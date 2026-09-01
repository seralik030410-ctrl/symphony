from __future__ import annotations

import base64
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator, field_validator

Text = Annotated[str, Field(max_length=8000)]
Label = Annotated[str, Field(min_length=1, max_length=160)]
Scalar = Annotated[StrictStr, Field(max_length=2000)] | StrictInt | StrictFloat | StrictBool | None
Format = Literal["pdf", "xlsx", "docx", "pptx"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class TableSpec(StrictModel):
    columns: list[Label] = Field(min_length=1, max_length=8)
    rows: list[list[Scalar]] = Field(default_factory=list, max_length=150)

    @model_validator(mode="after")
    def rectangular(self):
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("Every table row must match the columns")
        return self


class ChartSpec(StrictModel):
    title: Label
    kind: Literal["bar", "line"] = "bar"
    labels: list[Label] = Field(min_length=1, max_length=12)
    values: list[float] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def same_length(self):
        if len(self.labels) != len(self.values):
            raise ValueError("Chart labels and values must have the same length")
        if any(abs(value) > 1e12 for value in self.values):
            raise ValueError("Chart values exceed supported bounds")
        return self


class ImageSpec(StrictModel):
    png_base64: str = Field(max_length=2_800_000)
    caption: Label

    @field_validator("png_base64")
    @classmethod
    def png_only(cls, value):
        raw = base64.b64decode(value, validate=True)
        if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) > 2_000_000:
            raise ValueError("Only PNG images up to 2 MB are accepted; no paths or remote URLs")
        return value


class SectionSpec(StrictModel):
    heading: Label
    paragraphs: list[Text] = Field(default_factory=list, max_length=20)
    bullets: list[Text] = Field(default_factory=list, max_length=20)
    table: TableSpec | None = None
    chart: ChartSpec | None = None
    image: ImageSpec | None = None
    callout: Text | None = None


class ReportSpec(StrictModel):
    title: Label
    subtitle: Text = ""
    preset: Literal["clean_report", "finance_report", "technical_report", "visual_brief"] = "clean_report"
    sections: list[SectionSpec] = Field(min_length=1, max_length=30)
    citations: list[Annotated[str, Field(max_length=1000)]] = Field(default_factory=list, max_length=40)


class DocumentSpec(ReportSpec):
    header: Annotated[str, Field(max_length=160)] = ""
    footer: Annotated[str, Field(max_length=160)] = "Symphony"


class ColumnSpec(StrictModel):
    name: Label
    type: Literal["text", "number", "boolean", "date"] = "text"
    format: Literal["general", "integer", "decimal", "currency", "percent", "date"] = "general"
    width: float = Field(default=22, ge=8, le=60)


class SheetSpec(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=31, pattern=r"^[^\[\]:*?/\\']+$")]
    columns: list[ColumnSpec] = Field(min_length=1, max_length=24)
    rows: list[list[Scalar]] = Field(default_factory=list, max_length=2000)
    formulas: dict[str, Annotated[str, Field(max_length=500)]] = Field(default_factory=dict, max_length=2000)

    @model_validator(mode="after")
    def values_match_columns(self):
        from datetime import date
        if len(set(column.name for column in self.columns)) != len(self.columns):
            raise ValueError("Column names must be unique")
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError("Every row must match columns; row 1 is the generated header")
            for col, value in zip(self.columns, row):
                if value is None:
                    continue
                if col.type == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
                    raise ValueError(f"{col.name}: expected number")
                if col.type == "boolean" and not isinstance(value, bool):
                    raise ValueError(f"{col.name}: expected boolean")
                if col.type in {"text", "date"} and not isinstance(value, str):
                    raise ValueError(f"{col.name}: expected string")
                if col.type == "date":
                    date.fromisoformat(value)
        return self


class WorkbookSpec(StrictModel):
    title: Label
    sheets: list[SheetSpec] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def unique_sheets(self):
        if len({sheet.name.casefold() for sheet in self.sheets}) != len(self.sheets):
            raise ValueError("Sheet names must be unique (case-insensitive)")
        return self


class Slide(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=100)]
    subtitle: Annotated[str, Field(max_length=300)] = ""
    bullets: list[Annotated[str, Field(max_length=180)]] = Field(default_factory=list, max_length=6)
    table: TableSpec | None = None
    chart: ChartSpec | None = None
    image: ImageSpec | None = None
    notes: Text = ""

    @model_validator(mode="after")
    def bounded_layout(self):
        if sum(bool(item) for item in (self.bullets, self.table, self.chart, self.image)) > 1:
            raise ValueError("Use one body layout per slide: bullets, table, chart or image")
        if self.table and (len(self.table.rows) > 10 or len(self.table.columns) > 5):
            raise ValueError("Slide tables support up to 10 rows and 5 columns")
        if self.table and any(len(str(v or "")) > 100 for row in self.table.rows for v in row):
            raise ValueError("Slide table cells are limited to 100 characters")
        return self


class SlideSpec(StrictModel):
    title: Label
    preset: Literal["clean_report", "finance_report", "technical_report", "visual_brief"] = "visual_brief"
    slides: list[Slide] = Field(min_length=1, max_length=30)


SCHEMAS = {"pdf": ReportSpec, "xlsx": WorkbookSpec, "docx": DocumentSpec, "pptx": SlideSpec}
EXAMPLES = {
    "pdf": {"title": "Отчёт", "sections": [{"heading": "Итоги", "paragraphs": ["Проверенные факты и выводы."]}]},
    "docx": {"title": "Документ", "sections": [{"heading": "Раздел", "paragraphs": ["Содержание."]}]},
    "xlsx": {"title": "Бюджет", "sheets": [{"name": "Бюджет", "columns": [{"name": "Статья"}, {"name": "Сумма", "type": "number", "format": "currency"}], "rows": [["План", 100], ["Итого", None]], "formulas": {"B3": "=SUM(B2:B2)"}}]},
    "pptx": {"title": "Презентация", "slides": [{"title": "Итоги", "bullets": ["Главный вывод", "Следующий шаг"]}]},
}


def parse_spec(format: str, value: dict):
    if format not in SCHEMAS:
        raise ValueError("Unsupported document format")
    return SCHEMAS[format].model_validate(value)
