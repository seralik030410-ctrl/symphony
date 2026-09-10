from __future__ import annotations

import re
from typing import Any

from pydantic import Field, field_validator

from backend.tools.contracts import Tool, ToolContext, ToolInput, ToolResult


CAPABILITY_ALIASES = {
    "fs.write": "create write new file text",
    "fs.apply_patch": "edit modify change patch existing file code",
    "sandbox.shell": "command terminal test build run execute",
    "sandbox.preview": "preview website html browser",
    "web.search": "internet research current search sources",
    "web.open": "internet open read page url source",
    "artifact.render": "document pdf word docx spreadsheet xlsx powerpoint pptx",
    "artifact.inspect": "inspect document pdf spreadsheet presentation",
    "artifact.read_table": "csv excel xlsx table spreadsheet data",
    "office.inspect": "inspect analyze parse document word docx excel xlsx spreadsheet powerpoint pptx presentation pdf tables sheets formulas slides notes",
    "office.create": "create make generate document word docx excel xlsx spreadsheet powerpoint pptx presentation report financial deck",
    "office.patch": "edit patch update modify cell formula table paragraph slide word excel presentation document docx xlsx pptx",
    "office.convert": "convert transform markdown docx pdf xlsx csv format conversion",
    "context.index_file": "large file index document source",
    "context.search": "search indexed documents retrieval",
    "vision.ocr": "image text ocr scan recognize",
    "skill.read_resource": "skill resource instructions reference",
    "skill.run_script": "skill script execute",
    "agent.execute_batch": "batch repeat many operations",
    "agent.propose_learning": "memory skill learning proposal",
}


class ToolSearchInput(ToolInput):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=6, ge=1, le=12)

    @field_validator("query")
    @classmethod
    def nonempty_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Tool search query cannot be empty")
        return value


class ToolSearchTool(Tool):
    name = "tool.search"
    title = "Find available tools"
    description = (
        "Search the registered tool catalog by capability and activate matching tools for later steps. "
        "Use this when the needed specialist tool is not currently exposed."
    )
    input_model = ToolSearchInput
    read_only = True

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    async def execute(self, context: ToolContext, arguments: ToolSearchInput) -> ToolResult:
        matches = self.registry.search_catalog(
            arguments.query, allowed_names=context.allowed_tool_names, limit=arguments.limit)
        return ToolResult({
            "query": arguments.query.strip(),
            "matches": matches,
            "activated_tools": [item["name"] for item in matches],
        })


def catalog_score(query: str, value: dict[str, Any]) -> tuple[int, str] | None:
    normalized = " ".join(query.casefold().split())
    tokens = set(re.findall(r"[\w.-]+", normalized))
    name = str(value["name"]).casefold()
    title = str(value.get("title") or "").casefold()
    description = (str(value.get("description") or "") + " " +
                   CAPABILITY_ALIASES.get(str(value["name"]), "")).casefold()
    if normalized == name:
        score = 1000
    elif name.startswith(normalized):
        score = 800
    elif normalized in name:
        score = 700
    elif normalized in title:
        score = 550
    elif normalized in description:
        score = 400
    else:
        haystack = set(re.findall(r"[\w.-]+", f"{name} {title} {description}"))
        overlap = len(tokens & haystack)
        partial = sum(1 for token in tokens if len(token) >= 3 and any(
            token in candidate or candidate in token for candidate in haystack if len(candidate) >= 3))
        if not overlap and not partial:
            return None
        score = 100 + overlap * 20 + partial * 8
    return score, name
