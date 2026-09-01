from __future__ import annotations

import difflib
import fnmatch
import os
import re
import uuid
from pathlib import Path

from pydantic import Field

from backend.tools.contracts import Tool, ToolContext, ToolError, ToolInput, ToolResult
from backend.tools.workspace import WorkspaceManager, is_link, walk_files


MAX_TEXT_BYTES = 200_000


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise ToolError("not_a_file", f"Expected a file: {path.name}")
    size = path.stat().st_size
    if size > MAX_TEXT_BYTES:
        raise ToolError("file_too_large", f"Text file exceeds {MAX_TEXT_BYTES} bytes")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError("binary_file", "Only UTF-8 text files are supported in Stage 2") from exc


def _diff(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


class ListInput(ToolInput):
    path: str = Field(default=".", max_length=500)
    max_entries: int = Field(default=200, ge=1, le=500)


class ListFilesTool(Tool):
    name = "fs.list"
    title = "List workspace files"
    description = "List files and directories inside the current chat workspace. Never lists other chats."
    input_model = ListInput

    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces

    async def execute(self, context: ToolContext, arguments: ListInput) -> ToolResult:
        directory = self.workspaces.resolve(context.session_id, arguments.path, must_exist=True)
        if not directory.is_dir():
            raise ToolError("not_a_directory", "fs.list requires a directory path")
        root = self.workspaces.session_root(context.session_id)
        entries: list[dict[str, object]] = []
        for current_root, directories, files in os.walk(directory, followlinks=False):
            directories[:] = sorted(
                name for name in directories if not is_link(Path(current_root) / name)
            )
            for name in [*directories, *sorted(files)]:
                path = Path(current_root) / name
                if is_link(path):
                    continue
                entries.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "type": "directory" if path.is_dir() else "file",
                        "size": path.stat().st_size if path.is_file() else None,
                    }
                )
                if len(entries) >= arguments.max_entries:
                    return ToolResult({"entries": entries, "truncated": True})
        return ToolResult({"entries": entries, "truncated": False})


class ReadInput(ToolInput):
    path: str = Field(min_length=1, max_length=500)


class ReadFileTool(Tool):
    name = "fs.read"
    title = "Read text file"
    description = "Read one UTF-8 text file from the current chat workspace."
    input_model = ReadInput

    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces

    async def execute(self, context: ToolContext, arguments: ReadInput) -> ToolResult:
        path = self.workspaces.resolve(context.session_id, arguments.path, must_exist=True)
        content = _read_text(path)
        return ToolResult({"path": arguments.path, "content": content, "characters": len(content)})


class WriteInput(ToolInput):
    path: str = Field(min_length=1, max_length=500)
    content: str = Field(max_length=MAX_TEXT_BYTES)
    overwrite: bool = False


class WriteFileTool(Tool):
    name = "fs.write"
    title = "Write text file"
    description = "Create a UTF-8 text file, or replace it only when overwrite is true. Parent folders are created."
    input_model = WriteInput
    read_only = False

    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces

    async def execute(self, context: ToolContext, arguments: WriteInput) -> ToolResult:
        path = self.workspaces.resolve(context.session_id, arguments.path)
        existed = path.exists()
        if path.exists() and path.is_dir():
            raise ToolError("not_a_file", "Cannot write over a directory")
        if path.exists() and not arguments.overwrite:
            raise ToolError("already_exists", "File exists; set overwrite=true or use fs.apply_patch")
        before = _read_text(path) if path.exists() else ""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".symphony-{uuid.uuid4().hex}.tmp")
        temporary.write_text(arguments.content, encoding="utf-8", newline="")
        temporary.replace(path)
        relative = self.workspaces.relative(context.session_id, path)
        return ToolResult(
            {"path": relative, "characters": len(arguments.content), "created": not existed},
            changed_files=[relative],
            diff=_diff(relative, before, arguments.content),
        )


class PatchInput(ToolInput):
    path: str = Field(min_length=1, max_length=500)
    old_text: str = Field(min_length=1, max_length=MAX_TEXT_BYTES)
    new_text: str = Field(max_length=MAX_TEXT_BYTES)
    replace_all: bool = False


class ApplyPatchTool(Tool):
    name = "fs.apply_patch"
    title = "Apply exact text patch"
    description = "Replace exact text in an existing UTF-8 file. Fails on missing or ambiguous text unless replace_all is true."
    input_model = PatchInput
    read_only = False

    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces

    async def execute(self, context: ToolContext, arguments: PatchInput) -> ToolResult:
        path = self.workspaces.resolve(context.session_id, arguments.path, must_exist=True)
        before = _read_text(path)
        occurrences = before.count(arguments.old_text)
        if occurrences == 0:
            raise ToolError("text_not_found", "old_text was not found in the file")
        if occurrences > 1 and not arguments.replace_all:
            raise ToolError("ambiguous_patch", "old_text occurs more than once; provide more context or set replace_all")
        after = before.replace(
            arguments.old_text,
            arguments.new_text,
            -1 if arguments.replace_all else 1,
        )
        temporary = path.with_name(f".symphony-{uuid.uuid4().hex}.tmp")
        temporary.write_text(after, encoding="utf-8", newline="")
        temporary.replace(path)
        relative = self.workspaces.relative(context.session_id, path)
        return ToolResult(
            {"path": relative, "replacements": occurrences if arguments.replace_all else 1},
            changed_files=[relative],
            diff=_diff(relative, before, after),
        )


class SearchInput(ToolInput):
    query: str = Field(min_length=1, max_length=500)
    path: str = Field(default=".", max_length=500)
    glob: str = Field(default="*", max_length=200)
    regex: bool = False
    max_results: int = Field(default=100, ge=1, le=500)


class SearchTool(Tool):
    name = "search.rg"
    title = "Search workspace text"
    description = "Search UTF-8 text files in the current chat workspace with literal text or a regular expression."
    input_model = SearchInput

    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces

    async def execute(self, context: ToolContext, arguments: SearchInput) -> ToolResult:
        directory = self.workspaces.resolve(context.session_id, arguments.path, must_exist=True)
        if not directory.is_dir():
            raise ToolError("not_a_directory", "search.rg requires a directory path")
        try:
            pattern = re.compile(arguments.query if arguments.regex else re.escape(arguments.query))
        except re.error as exc:
            raise ToolError("invalid_regex", str(exc)) from exc
        root = self.workspaces.session_root(context.session_id)
        matches: list[dict[str, object]] = []
        for path in walk_files(directory):
            relative = path.relative_to(root).as_posix()
            if not fnmatch.fnmatch(path.name, arguments.glob) and not fnmatch.fnmatch(relative, arguments.glob):
                continue
            if path.stat().st_size > MAX_TEXT_BYTES:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, 1):
                if pattern.search(line):
                    matches.append({"path": relative, "line": line_number, "text": line[:500]})
                    if len(matches) >= arguments.max_results:
                        return ToolResult({"matches": matches, "truncated": True})
        return ToolResult({"matches": matches, "truncated": False})
