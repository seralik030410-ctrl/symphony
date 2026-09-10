from __future__ import annotations

import hashlib
import io
import json
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from backend.providers.secrets import SENSITIVE_KEY
from backend.storage.database import Database, utc_now
from backend.storage.repository import ConflictError, NotFoundError
from backend.tools.contracts import ToolError
from backend.tools.workspace import is_link


ASSET_ID = re.compile(r"^[0-9a-f]{32}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_ASSET_BYTES = 100_000_000
MIME_KIND = {
    "image/png": "image", "image/jpeg": "image", "image/webp": "image", "image/gif": "image",
    "video/mp4": "video", "video/webm": "video", "audio/wav": "audio", "audio/mpeg": "audio",
    "audio/webm": "audio", "audio/ogg": "audio", "audio/mp4": "audio",
}


def _valid_signature(raw: bytes, mime_type: str) -> bool:
    return {
        "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
        "image/webp": len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP",
        "image/gif": raw.startswith((b"GIF87a", b"GIF89a")),
        "video/mp4": len(raw) >= 12 and raw[4:8] == b"ftyp",
        "video/webm": raw.startswith(b"\x1aE\xdf\xa3"),
        "audio/wav": len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WAVE",
        "audio/mpeg": raw.startswith(b"ID3") or (len(raw) >= 2 and raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0),
        "audio/webm": raw.startswith(b"\x1aE\xdf\xa3"),
        "audio/ogg": raw.startswith(b"OggS"),
        "audio/mp4": len(raw) >= 12 and raw[4:8] == b"ftyp",
    }.get(mime_type, False)


def _validate_metadata(value: Any, *, depth: int = 0) -> None:
    if depth > 8:
        raise ToolError("invalid_provenance", "Media provenance is too deeply nested")
    if isinstance(value, dict):
        if any(SENSITIVE_KEY.search(str(key)) for key in value):
            raise ToolError("invalid_provenance", "Media provenance cannot contain secrets")
        for item in value.values():
            _validate_metadata(item, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            _validate_metadata(item, depth=depth + 1)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ToolError("invalid_provenance", "Media provenance must contain JSON values only")


class MediaAssetStore:
    def __init__(self, database: Database, root: Path) -> None:
        self.database = database
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if is_link(self.root):
            raise ToolError("invalid_media_root", "Media root cannot be a link")
        (self.root / "blobs").mkdir(exist_ok=True)
        (self.root / "previews").mkdir(exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, relative: str, *, must_exist: bool = False) -> Path:
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or ":" in relative or "\\" in relative:
            raise ToolError("invalid_media_path", "Invalid managed media path")
        candidate = (self.root / rel).resolve(strict=False)
        if self.root not in candidate.parents or is_link(candidate):
            raise ToolError("invalid_media_path", "Media path escapes its managed root")
        if must_exist and not candidate.is_file():
            raise NotFoundError("Media file not found")
        return candidate

    @staticmethod
    def _describe(row: Any) -> dict[str, Any]:
        value = dict(row)
        value["provenance"] = json.loads(value.pop("provenance_json"))
        value["download_url"] = f"/api/sessions/{value['session_id']}/media/assets/{value['id']}/content"
        value["preview_url"] = (
            f"/api/sessions/{value['session_id']}/media/assets/{value['id']}/preview"
            if value.get("preview_path") else None
        )
        return value

    def list(self, session_id: str, *, deleted: bool = False) -> list[dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT * FROM media_assets WHERE session_id=? AND deleted_at IS " +
                ("NOT NULL" if deleted else "NULL") + " ORDER BY created_at DESC,id DESC",
                (session_id,),
            ).fetchall()
        return [self._describe(row) for row in rows]

    def get(self, session_id: str, asset_id: str, *, include_deleted: bool = False) -> dict[str, Any]:
        if not ASSET_ID.fullmatch(asset_id):
            raise NotFoundError("Media asset not found")
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM media_assets WHERE id=? AND session_id=?" + ("" if include_deleted else " AND deleted_at IS NULL"),
                (asset_id, session_id),
            ).fetchone()
        if not row:
            raise NotFoundError("Media asset not found in this chat")
        return self._describe(row)

    def _write_blob(self, sha256: str, raw: bytes) -> str:
        relative = f"blobs/{sha256[:2]}/{sha256}"
        destination = self._path(relative)
        destination.parent.mkdir(exist_ok=True)
        if destination.exists():
            if is_link(destination) or destination.stat().st_size != len(raw) or hashlib.sha256(destination.read_bytes()).hexdigest() != sha256:
                raise ToolError("media_integrity_error", "A managed media blob failed integrity validation")
            return relative
        temporary = destination.with_name(f".{sha256}-{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return relative

    def _make_preview(self, asset_id: str, raw: bytes, mime_type: str, filename: str) -> tuple[str, int | None, int | None]:
        relative = f"previews/{asset_id}.jpg"
        destination = self._path(relative)
        temporary = destination.with_name(f".{asset_id}-{uuid.uuid4().hex}.tmp")
        if mime_type.startswith("image/"):
            try:
                with Image.open(io.BytesIO(raw)) as source:
                    source.seek(0)
                    source.load()
                    width, height = source.size
                    image = source.convert("RGBA")
                    background = Image.new("RGB", image.size, "#f3f5f7")
                    background.paste(image, mask=image.getchannel("A"))
                    background.thumbnail((640, 640), Image.Resampling.LANCZOS)
                    background.save(temporary, "JPEG", quality=84, optimize=True)
                    temporary.replace(destination)
                return relative, width, height
            except (OSError, ValueError) as exc:
                raise ToolError("invalid_media", "Image decoder rejected the uploaded file") from exc
            finally:
                temporary.unlink(missing_ok=True)
        canvas = Image.new("RGB", (640, 360), "#182027")
        draw = ImageDraw.Draw(canvas)
        label = "VIDEO" if mime_type.startswith("video/") else "AUDIO"
        draw.text((32, 150), label, fill="#fdfefe")
        draw.text((32, 184), filename[:72], fill="#aab3bb")
        try:
            canvas.save(temporary, "JPEG", quality=82, optimize=True)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return relative, None, None

    def put(self, session_id: str, raw: bytes, *, filename: str, mime_type: str, source: str,
            provenance: dict[str, Any] | None = None, provider_profile_id: str | None = None,
            model: str | None = None) -> tuple[dict[str, Any], bool]:
        if mime_type not in MIME_KIND or not _valid_signature(raw, mime_type):
            raise ToolError("invalid_media", "File content does not match an allowed media MIME type")
        if not raw or len(raw) > MAX_ASSET_BYTES:
            raise ToolError("media_too_large", "Media file must be between 1 byte and 100 MB")
        if not filename or len(filename) > 180 or re.search(r"[/\\:\x00]", filename):
            raise ToolError("invalid_filename", "Media filename is invalid")
        provenance = provenance or {}
        _validate_metadata(provenance)
        encoded = json.dumps(provenance, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 64_000:
            raise ToolError("invalid_provenance", "Media provenance exceeds 64 KB")
        sha256 = hashlib.sha256(raw).hexdigest()
        with self._lock:
            with self.database.read() as connection:
                existing = connection.execute(
                    "SELECT * FROM media_assets WHERE session_id=? AND sha256=? AND mime_type=? AND deleted_at IS NULL",
                    (session_id, sha256, mime_type),
                ).fetchone()
            if existing:
                return self._describe(existing), False
            blob_path = self._write_blob(sha256, raw)
            asset_id = uuid.uuid4().hex
            try:
                preview_path, width, height = self._make_preview(asset_id, raw, mime_type, filename)
                now = utc_now()
                with self.database.transaction() as connection:
                    session = connection.execute("SELECT 1 FROM sessions WHERE id=? AND deleted_at IS NULL", (session_id,)).fetchone()
                    if not session:
                        raise NotFoundError("Session not found")
                    connection.execute(
                        """INSERT INTO media_assets(id,session_id,kind,filename,mime_type,size,sha256,blob_path,
                           preview_path,preview_mime_type,width,height,source,provider_profile_id,model,provenance_json,
                           created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,'image/jpeg',?,?,?,?,?,?,?,?)""",
                        (asset_id, session_id, MIME_KIND[mime_type], filename, mime_type, len(raw), sha256, blob_path,
                         preview_path, width, height, source[:80], provider_profile_id, model, encoded, now, now),
                    )
            except Exception:
                self._path(f"previews/{asset_id}.jpg").unlink(missing_ok=True)
                with self.database.read() as connection:
                    referenced = connection.execute("SELECT 1 FROM media_assets WHERE blob_path=?", (blob_path,)).fetchone()
                if not referenced:
                    self._path(blob_path).unlink(missing_ok=True)
                raise
        return self.get(session_id, asset_id), True

    def verified_file(self, session_id: str, asset_id: str, *, preview: bool = False) -> tuple[Path, dict[str, Any]]:
        asset = self.get(session_id, asset_id)
        relative = asset["preview_path"] if preview else asset["blob_path"]
        if not relative:
            raise NotFoundError("Media preview not found")
        path = self._path(relative, must_exist=True)
        if not preview and (path.stat().st_size != asset["size"] or hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]):
            raise ToolError("media_integrity_error", "Saved media is missing or changed")
        return path, asset

    def regenerate_preview(self, session_id: str, asset_id: str) -> dict[str, Any]:
        path, asset = self.verified_file(session_id, asset_id)
        preview_path, width, height = self._make_preview(asset_id, path.read_bytes(), asset["mime_type"], asset["filename"])
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE media_assets SET preview_path=?,preview_mime_type='image/jpeg',width=COALESCE(?,width),height=COALESCE(?,height),updated_at=? WHERE id=? AND session_id=?",
                (preview_path, width, height, utc_now(), asset_id, session_id),
            )
        return self.get(session_id, asset_id)

    def trash(self, session_id: str, asset_id: str) -> dict[str, Any]:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE media_assets SET deleted_at=COALESCE(deleted_at,?),updated_at=? WHERE id=? AND session_id=?",
                (utc_now(), utc_now(), asset_id, session_id),
            )
        if not cursor.rowcount:
            raise NotFoundError("Media asset not found in this chat")
        return {"id": asset_id, "recoverable": True}

    def restore(self, session_id: str, asset_id: str) -> dict[str, Any]:
        asset = self.get(session_id, asset_id, include_deleted=True)
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    "UPDATE media_assets SET deleted_at=NULL,updated_at=? WHERE id=? AND session_id=? AND deleted_at IS NOT NULL",
                    (utc_now(), asset_id, session_id),
                )
                if not cursor.rowcount:
                    raise ConflictError("Media asset is not in trash")
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise ConflictError("An identical active media asset already exists in this chat") from exc
            raise
        return self.get(session_id, asset_id)

    def purge(self, session_id: str, asset_id: str) -> dict[str, Any]:
        with self._lock:
            asset = self.get(session_id, asset_id, include_deleted=True)
            if not asset["deleted_at"]:
                raise ConflictError("Move the media asset to trash before deleting it permanently")
            with self.database.transaction() as connection:
                connection.execute("DELETE FROM media_assets WHERE id=? AND session_id=?", (asset_id, session_id))
                blob_referenced = connection.execute("SELECT 1 FROM media_assets WHERE blob_path=? LIMIT 1", (asset["blob_path"],)).fetchone()
            if asset.get("preview_path"):
                self._path(asset["preview_path"]).unlink(missing_ok=True)
            if not blob_referenced:
                self._path(asset["blob_path"]).unlink(missing_ok=True)
        return {"id": asset_id, "recoverable": False}

    def link(self, session_id: str, asset_id: str, *, relation: str, turn_id: str | None = None,
             job_id: str | None = None) -> dict[str, Any]:
        self.get(session_id, asset_id)
        with self.database.transaction() as connection:
            if job_id:
                existing = connection.execute(
                    "SELECT id FROM media_links WHERE asset_id=? AND session_id=? AND job_id=? AND relation=?",
                    (asset_id, session_id, job_id, relation[:80]),
                ).fetchone()
                if existing:
                    return {"id": existing["id"], "asset_id": asset_id, "relation": relation[:80]}
            link_id = uuid.uuid4().hex
            connection.execute(
                "INSERT INTO media_links(id,asset_id,session_id,turn_id,job_id,relation,created_at) VALUES(?,?,?,?,?,?,?)",
                (link_id, asset_id, session_id, turn_id, job_id, relation[:80], utc_now()),
            )
        return {"id": link_id, "asset_id": asset_id, "relation": relation}
