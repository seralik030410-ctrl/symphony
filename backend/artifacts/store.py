from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

from backend.storage.database import Database, utc_now
from backend.storage.repository import NotFoundError
from backend.tools.contracts import ToolContext, ToolError
from backend.tools.workspace import WorkspaceManager, is_link
from .schemas import parse_spec

ID = re.compile(r"^[0-9a-f]{32}$")
MAX_SPEC_BYTES = 4_000_000


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArtifactStore:
    def __init__(self, database: Database, workspaces: WorkspaceManager, runner):
        self.database, self.workspaces, self.runner = database, workspaces, runner
        self._locks: dict[str, asyncio.Lock] = {}

    def root(self, session_id):
        path = self.workspaces.session_root(session_id).parent / "artifacts"
        if is_link(path): raise ToolError("invalid_path", "Artifact root cannot be a link")
        path.mkdir(exist_ok=True)
        return path

    def folder(self, session_id, artifact_id, version):
        if not ID.fullmatch(artifact_id) or not isinstance(version, int) or version < 1:
            raise NotFoundError("Artifact not found")
        root = self.root(session_id)
        folder = root / artifact_id / str(version)
        if is_link(folder.parent) or is_link(folder): raise ToolError("invalid_path", "Artifact path cannot be a link")
        return folder

    def list(self, session_id):
        with self.database.read() as conn:
            rows = conn.execute("SELECT a.id, a.format, v.* FROM artifacts a JOIN artifact_versions v ON v.artifact_id=a.id WHERE a.session_id=? ORDER BY v.created_at DESC, v.version DESC", (session_id,)).fetchall()
        return [self._describe(session_id, row) for row in rows]

    @staticmethod
    def _describe(session_id, row):
        manifest = json.loads(row["manifest_json"])
        base = f"/api/sessions/{session_id}/artifacts/{row['id']}/versions/{row['version']}"
        return {"id": row["id"], "version": row["version"], "turn_id": row["turn_id"], "title": row["title"], "format": row["format"], "created_at": row["created_at"],
                "download_url": f"{base}/files/{manifest['output']}", "detail_url": base,
                "preview_pages": len(manifest.get("pages", [])), "size": manifest["files"][manifest["output"]]["size"],
                "valid": manifest["valid"]}

    def get(self, session_id, artifact_id, version=None):
        if not ID.fullmatch(artifact_id): raise NotFoundError("Artifact not found")
        with self.database.read() as conn:
            row = conn.execute("SELECT a.id, a.format, v.* FROM artifacts a JOIN artifact_versions v ON v.artifact_id=a.id WHERE a.session_id=? AND a.id=? AND (? IS NULL OR v.version=?) ORDER BY v.version DESC LIMIT 1", (session_id, artifact_id, version, version)).fetchone()
        if row is None: raise NotFoundError("Artifact not found in this chat")
        result = self._describe(session_id, row)
        manifest = json.loads(row["manifest_json"])
        base = result["detail_url"]
        return {**result, "validation": manifest, "pages": [{**page, "url": f"{base}/files/{page['file']}"} for page in manifest.get("pages", [])],
                "tables": manifest.get("tables", []), "source_url": f"{base}/files/source.json", "recipe_url": f"{base}/files/recipe.json", "validation_url": f"{base}/files/validation.json"}

    def file(self, session_id, artifact_id, version, filename):
        detail = self.get(session_id, artifact_id, version)
        info = detail["validation"]["files"].get(filename)
        if not info or "/" in filename or "\\" in filename or ":" in filename: raise NotFoundError("Artifact file not found")
        path = self.folder(session_id, artifact_id, version) / filename
        if is_link(path) or not path.is_file() or path.stat().st_size != info["size"] or digest(path) != info["sha256"]:
            raise ToolError("artifact_integrity_error", "Saved artifact file is missing or changed; regenerate a new version")
        return path

    async def render(self, context: ToolContext, format: str, spec_path: str, artifact_id: str | None):
        path = self.workspaces.resolve(context.session_id, spec_path, must_exist=True)
        if not path.is_file() or path.stat().st_size > MAX_SPEC_BYTES: raise ToolError("invalid_spec", "Spec must be a JSON file no larger than 4 MB")
        try:
            source = json.loads(path.read_text(encoding="utf-8-sig"))
            spec = parse_spec(format, source)
            encoded = spec.model_dump_json(indent=2)
            if re.search(r"\\u00(?:0[0-8bef]|1[0-9a-f])", encoded, re.I): raise ValueError("Unsupported control character in document")
        except Exception as error:
            raise ToolError("invalid_document_spec", str(error)[:3000]) from error
        requested_id = artifact_id
        artifact_id = artifact_id or uuid.uuid4().hex
        if not ID.fullmatch(artifact_id): raise ToolError("invalid_artifact", "Invalid artifact id")
        key = context.session_id + artifact_id
        async with self._locks.setdefault(key, asyncio.Lock()):
            try:
                previous = self.get(context.session_id, artifact_id)
            except NotFoundError:
                previous = None
                if requested_id: raise
            if previous and previous["format"] != format: raise ToolError("artifact_format_mismatch", "A version cannot change document format")
            # A foreign chat's id cannot be reused to infer or overwrite its artifact.
            with self.database.read() as conn:
                if not previous and conn.execute("SELECT 1 FROM artifacts WHERE id=?", (artifact_id,)).fetchone(): raise NotFoundError("Artifact not found in this chat")
            version = previous["version"] + 1 if previous else 1
            root = self.root(context.session_id)
            job = root / (".job-" + uuid.uuid4().hex); job.mkdir()
            published = False
            try:
                (job / "source.json").write_text(encoded, encoding="utf-8")
                recipe = {"format": format, "renderer": "symphony-documents-v1", "runtime_image": self.runner.sandbox.image if hasattr(self.runner, "sandbox") else "test", "source_path": spec_path, "source_sha256": digest(job / "source.json"), "created_at": utc_now()}
                (job / "recipe.json").write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding="utf-8")
                await self.runner.render(job, context.on_output)
                # Cancellation before this point never publishes an artifact.
                await asyncio.sleep(0)
                manifest = json.loads((job / "validation.json").read_text(encoding="utf-8"))
                if not manifest.get("valid") or manifest.get("output") != f"document.{format}": raise ToolError("artifact_invalid", "Renderer validation failed")
                files = list(job.iterdir())
                if len(files) > 90 or any(is_link(file) or not file.is_file() for file in files) or sum(file.stat().st_size for file in files) > 100_000_000:
                    raise ToolError("artifact_too_large", "Document exceeds the artifact size limit")
                manifest["files"] = {file.name: {"size": file.stat().st_size, "sha256": digest(file)} for file in files}
                folder = self.folder(context.session_id, artifact_id, version)
                folder.parent.mkdir(exist_ok=True)
                if folder.exists(): raise ToolError("artifact_version_conflict", "Unpublished version exists; regenerate as a new artifact")
                with self.database.transaction() as conn:
                    turn = conn.execute("SELECT session_id, cancel_requested, status FROM turns WHERE id=?", (context.turn_id,)).fetchone()
                    if turn is None or turn["session_id"] != context.session_id: raise ToolError("invalid_turn", "Artifact must belong to its producing turn")
                    if turn["cancel_requested"]: raise asyncio.CancelledError
                    if not previous: conn.execute("INSERT INTO artifacts(id, session_id, format, created_at) VALUES (?,?,?,?)", (artifact_id, context.session_id, format, utc_now()))
                    conn.execute("INSERT INTO artifact_versions(artifact_id, version, turn_id, title, manifest_json, created_at) VALUES (?,?,?,?,?,?)", (artifact_id, version, context.turn_id, spec.title, json.dumps(manifest, ensure_ascii=False), utc_now()))
                    job.rename(folder)
                published = True
                return self._compact(self.get(context.session_id, artifact_id, version))
            finally:
                # Exact per-job cleanup only. Never remove source/worktree or published versions.
                if not published and job.exists() and job.parent == root and job.name.startswith(".job-"):
                    shutil.rmtree(job)

    @staticmethod
    def _compact(detail):
        return {key: detail[key] for key in ("id", "version", "title", "format", "download_url", "detail_url", "preview_pages", "size", "valid")}
