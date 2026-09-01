"""Small, non-evaluating Excel formula interpreter. No Python eval or external links."""
from __future__ import annotations

import ast
import math
import operator
import re

from openpyxl.formula import Tokenizer
from openpyxl.utils.cell import column_index_from_string, range_boundaries

from .schemas import WorkbookSpec

FUNCTIONS = {"SUM", "AVERAGE", "MIN", "MAX", "COUNT", "ROUND", "ABS"}
CELL = re.compile(r"^\$?([A-Z]{1,3})\$?([1-9][0-9]*)$")


def calculate(spec: WorkbookSpec) -> dict:
    sheets = {sheet.name.casefold(): sheet for sheet in spec.sheets}
    cache, visiting = {}, set()
    budget = [100_000]

    def locate(sheet_name, address):
        sheet = sheets.get(sheet_name.casefold())
        match = CELL.fullmatch(address.upper())
        if not sheet or not match:
            raise ValueError(f"Invalid formula reference: {sheet_name}!{address}")
        col, row = column_index_from_string(match[1]), int(match[2])
        if row < 2 or row > len(sheet.rows) + 1 or col > len(sheet.columns):
            raise ValueError(f"Reference outside data: {sheet_name}!{address}")
        return sheet, col, row

    def cell(sheet_name, address):
        budget[0] -= 1
        if budget[0] < 0:
            raise ValueError("Formula computation budget exceeded")
        sheet, col, row = locate(sheet_name, address)
        address = address.upper().replace("$", "")
        key = (sheet.name, address)
        if key in visiting or len(visiting) >= 64:
            raise ValueError(f"Circular or too deeply nested formula at {sheet.name}!{address}")
        if key in cache:
            return cache[key]
        formula = sheet.formulas.get(address)
        if not formula:
            return sheet.rows[row - 2][col - 1]
        visiting.add(key)
        value = expression(formula, sheet.name)
        visiting.remove(key)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e100:
            raise ValueError(f"Non-finite or unsupported formula result: {key}")
        cache[key] = value
        return value

    def reference(value, current_sheet):
        if "!" in value:
            name, address = value.rsplit("!", 1)
            name = name.strip("'")
        else:
            name, address = current_sheet, value
        address = address.upper().replace("$", "")
        if ":" not in address:
            return cell(name, address)
        first, last = address.split(":", 1)
        locate(name, first); locate(name, last)
        left, top, right, bottom = range_boundaries(address)
        if left > right or top > bottom or (right - left + 1) * (bottom - top + 1) > 10_000:
            raise ValueError("Invalid or oversized formula range")
        from openpyxl.utils.cell import get_column_letter
        return [cell(name, f"{get_column_letter(c)}{r}") for r in range(top, bottom + 1) for c in range(left, right + 1)]

    def number(value):
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return value
        raise ValueError("Arithmetic requires numeric cells")

    def expression(formula, sheet_name):
        if not formula.startswith("=") or re.search(r"[\[\]{};|\\]", formula):
            raise ValueError("Formula must start with =; external links and array formulas are forbidden")
        parts = []
        for token in Tokenizer(formula).items:
            if token.type == "WHITE-SPACE":
                continue
            if token.type == "OPERAND" and token.subtype == "RANGE":
                parts.append(f"REF({token.value!r})")
            elif token.type == "OPERAND" and token.subtype == "NUMBER":
                parts.append(token.value)
            elif token.type == "FUNC" and token.subtype == "OPEN" and token.value[:-1].upper() in FUNCTIONS:
                parts.append(token.value.upper())
            elif token.type in {"PAREN", "FUNC"} and token.value in {"(", ")"}:
                parts.append(token.value)
            elif token.type == "SEP" and token.value == ",":
                parts.append(",")
            elif token.type in {"OPERATOR-INFIX", "OPERATOR-PREFIX"} and token.value in {"+", "-", "*", "/"}:
                parts.append(token.value)
            else:
                raise ValueError(f"Unsupported formula token {token.value!r}. Supported functions: {', '.join(sorted(FUNCTIONS))}")
        tree = ast.parse("".join(parts), mode="eval")

        def visit(node):
            if isinstance(node, ast.Expression):
                return visit(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
                return node.value
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                return number(visit(node.operand)) * (-1 if isinstance(node.op, ast.USub) else 1)
            if isinstance(node, ast.BinOp) and type(node.op) in {ast.Add, ast.Sub, ast.Mult, ast.Div}:
                return {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}[type(node.op)](number(visit(node.left)), number(visit(node.right)))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
                args = [visit(arg) for arg in node.args]
                name = node.func.id
                if name == "REF" and len(args) == 1 and isinstance(args[0], str):
                    return reference(args[0], sheet_name)
                flat = [v for arg in args for v in (arg if isinstance(arg, list) else [arg]) if isinstance(v, (int, float)) and not isinstance(v, bool)]
                if name == "SUM": return sum(flat)
                if name == "COUNT": return len(flat)
                if name == "AVERAGE" and flat: return sum(flat) / len(flat)
                if name == "MIN": return min(flat, default=0)
                if name == "MAX": return max(flat, default=0)
                if name == "ABS" and len(args) == 1: return abs(number(args[0]))
                if name == "ROUND" and len(args) == 2 and isinstance(args[1], int) and abs(args[1]) <= 10:
                    from decimal import Decimal, ROUND_HALF_UP
                    return float(Decimal(str(number(args[0]))).quantize(Decimal(10) ** -args[1], rounding=ROUND_HALF_UP))
            raise ValueError("Unsupported formula expression or arguments")
        return visit(tree)

    for sheet in spec.sheets:
        for address in sheet.formulas:
            if address != address.upper() or not CELL.fullmatch(address) or "$" in address:
                raise ValueError("Formula target must be an uppercase cell address, e.g. B4")
            _, col, row = locate(sheet.name, address)
            if sheet.rows[row - 2][col - 1] is not None:
                raise ValueError(
                    f"Formula target {sheet.name}!{address} is not an empty data cell. "
                    "Excel row 1 is the generated header, so rows[0] is row 2, rows[1] is row 3, etc. "
                    "Put null at the intended target in rows and use its Excel address; for three data rows "
                    "the last target is row 4. Formula ranges must start at row 2, never the header row 1."
                )
            cell(sheet.name, address)
    return {"engine": "symphony-safe-formulas-v1", "supported_functions": sorted(FUNCTIONS),
            "values": {f"{name}!{address}": value for (name, address), value in cache.items()},
            "formula_count": len(cache), "external_links": False}
