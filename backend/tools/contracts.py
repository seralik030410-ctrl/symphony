from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(slots=True)
class ToolResult:
    output: dict[str, Any]
    changed_files: list[str] = field(default_factory=list)
    diff: str | None = None


@dataclass(slots=True)
class ToolContext:
    session_id: str
    turn_id: str
    on_snapshot: Callable[[dict], Awaitable[None]] | None = None
    on_output: Callable[[dict], Awaitable[None]] | None = None
    selected_skill_ids: set[str] = field(default_factory=set)
    network_approved: bool = False
    on_event: Callable[[str, dict], Awaitable[None]] | None = None


class Tool(ABC):
    name: str
    title: str
    description: str
    input_model: type[ToolInput]
    read_only: bool = True
    destructive: bool = False
    open_world: bool = False
    timeout_seconds: float | None = None

    def dependency_fingerprint(self, context: ToolContext, arguments: dict[str, Any]) -> str | None:
        """Optional state dependency for duplicate protection, not an authorization bypass."""
        return None

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
            "annotations": {
                "readOnly": self.read_only,
                "destructive": self.destructive,
                "openWorld": self.open_world,
            },
            "timeout_seconds": self.timeout_seconds,
        }

    @abstractmethod
    async def execute(self, context: ToolContext, arguments: ToolInput) -> ToolResult:
        raise NotImplementedError
