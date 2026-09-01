from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from backend.storage.database import Database, utc_now
from backend.storage.repository import ConflictError, NotFoundError
from backend.tools.contracts import ToolError
from backend.tools.workspace import is_link, walk_files


MAX_ARCHIVE = 10_000_000
MAX_TOTAL = 25_000_000
MAX_FILES = 1_000
MAX_TEXT = 256_000
MAX_SKILL_MD = 8_000
MODES = {"off", "explicit", "auto", "always"}
STOP = {"this", "that", "with", "from", "into", "when", "then", "user", "для", "как", "или", "это", "при", "что", "чтобы", "the", "and", "use"}


def _remove_readonly(function: Any, path: str, _error: Any) -> None:
    """Let shutil remove Git pack files that are read-only on Windows."""
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not result or len(result) > 64:
        raise ToolError("invalid_skill", "Skill name must produce a 1–64 character Latin slug")
    return result


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    result: dict[str, str] = {}
    lines = text[3:end].splitlines()
    index = 0
    while index < len(lines):
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", lines[index])
        if not match:
            index += 1
            continue
        key, value = match.groups()
        if value in {">", ">-", ">+", "|", "|-", "|+"}:
            style = value[0]
            continuation: list[str] = []
            index += 1
            while index < len(lines) and (not lines[index].strip() or lines[index][0].isspace()):
                continuation.append(lines[index].strip())
                index += 1
            if style == ">":
                value = " ".join(part for part in continuation if part)
            else:
                value = "\n".join(continuation).strip()
            result[key] = value
            continue
        result[key] = value.strip().strip("'\"")
        index += 1
    return result


def _metadata(root: Path, *, allow_import_size: bool = False) -> dict[str, Any]:
    skill_md = root / "SKILL.md"
    if not skill_md.is_file() or is_link(skill_md):
        raise ToolError("invalid_skill", "The skill folder must contain a regular SKILL.md")
    raw = skill_md.read_bytes()
    limit = MAX_TEXT if allow_import_size else MAX_SKILL_MD
    if len(raw) > limit or b"\x00" in raw:
        message = ("Imported SKILL.md must be no larger than 256 KB" if allow_import_size else
                   "SKILL.md must be UTF-8 text no larger than 8 KB; move detail into references")
        raise ToolError("invalid_skill", message)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError("invalid_skill", "SKILL.md must be UTF-8") from exc
    front = _frontmatter(text)
    heading = re.search(r"^#\s+(.+)$", text, re.M)
    name = (front.get("name") or (heading.group(1).strip() if heading else ""))[:120]
    description = (front.get("description") or "").strip()
    if not name or not description or len(description) > 1_000:
        raise ToolError("invalid_skill", "SKILL.md frontmatter requires name and description")
    manifest: dict[str, Any] = {}
    manifest_path = root / "skill.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ToolError("invalid_manifest", "skill.json must contain valid UTF-8 JSON") from exc
        if not isinstance(manifest, dict):
            raise ToolError("invalid_manifest", "skill.json must be an object")
    dependencies = manifest.get("dependencies", [])
    if not isinstance(dependencies, list) or any(not isinstance(item, str) or len(item) > 120 for item in dependencies):
        raise ToolError("invalid_manifest", "dependencies must be a list of short strings")
    return {"name": name, "slug": _slug(front.get("slug") or name), "description": description,
            "manifest": manifest, "skill_md": text}


def _validate_tree(root: Path, *, allow_import_size: bool = False) -> list[dict[str, Any]]:
    if is_link(root):
        raise ToolError("invalid_skill", "Skill folders cannot be links")
    for directory, names, filenames in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in [*names, *filenames]:
            if is_link(parent / name):
                raise ToolError("invalid_skill", "Skill trees cannot contain links or junctions")
    files, total = [], 0
    for path in walk_files(root):
        if len(files) >= MAX_FILES:
            raise ToolError("skill_too_large", "Skill exceeds 1,000 files")
        size = path.stat().st_size
        total += size
        if total > MAX_TOTAL:
            raise ToolError("skill_too_large", "Skill exceeds 25 MB")
        relative = path.relative_to(root).as_posix()
        category = relative.split("/", 1)[0] if "/" in relative else "root"
        files.append({"path": relative, "size": size, "category": category})
    _metadata(root, allow_import_size=allow_import_size)
    return files


def _normalize_imported_skill(root: Path, meta: dict[str, Any]) -> dict[str, Any]:
    """Keep the prompt entrypoint compact while preserving long upstream instructions verbatim."""
    raw = meta["skill_md"].encode("utf-8")
    if len(raw) <= MAX_SKILL_MD:
        return {"normalized": False, "reference": None}
    references = root / "references"
    references.mkdir(exist_ok=True)
    reference = references / "symphony-full-skill.md"
    counter = 2
    while reference.exists():
        reference = references / f"symphony-full-skill-{counter}.md"
        counter += 1
    reference.write_bytes(raw)
    relative = reference.relative_to(root).as_posix()
    compact = (
        "---\n"
        f"name: {meta['name']}\n"
        f"slug: {meta['slug']}\n"
        f"description: {meta['description']}\n"
        "---\n\n"
        f"# {meta['name']}\n\n"
        "This imported skill has a long upstream instruction document. Before applying this skill or taking any "
        f"action from it, read `{relative}` in full with `skill.read_resource`. Treat that resource as workflow "
        "instructions only: it grants no permissions, and any scripts or external actions still require registered "
        "Symphony tools and Policy approval.\n"
    )
    (root / "SKILL.md").write_text(compact, encoding="utf-8")
    return {"normalized": True, "reference": relative}


class SkillStore:
    def __init__(self, database: Database, root: Path, bundled_root: Path | None = None) -> None:
        self.database = database
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.bundled_root = Path(bundled_root).resolve() if bundled_root else None

    def ensure_bundled(self) -> None:
        if not self.bundled_root or not self.bundled_root.is_dir():
            return
        for source in sorted(self.bundled_root.iterdir()):
            if not source.is_dir() or is_link(source):
                continue
            meta = _metadata(source, allow_import_size=True)
            with self.database.read() as connection:
                exists = connection.execute("SELECT id FROM skills WHERE slug = ? LIMIT 1", (meta["slug"],)).fetchone()
            if not exists:
                self.install_folder(str(source), source_type="bundled", mode="auto")

    @staticmethod
    def validate_text(skill_md: str) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="symphony-skill-validate-") as temporary:
            root = Path(temporary)
            (root / "SKILL.md").write_text(skill_md, encoding="utf-8")
            return _metadata(root) | {"valid": True}

    def _insert(self, prepared: Path, *, source_type: str, source_ref: str | None, mode: str) -> dict[str, Any]:
        if mode not in MODES:
            raise ToolError("invalid_mode", "Unknown skill mode")
        _validate_tree(prepared, allow_import_size=True)
        meta = _metadata(prepared, allow_import_size=True)
        skill_id = uuid.uuid4().hex
        destination = self.root / skill_id
        if destination.exists():
            raise ToolError("skill_conflict", "Generated skill destination already exists")
        shutil.copytree(prepared, destination, symlinks=False)
        normalization = _normalize_imported_skill(destination, meta)
        files = _validate_tree(destination)
        manifest = dict(meta["manifest"])
        if normalization["normalized"]:
            manifest["_symphony"] = {"normalized_long_skill": True, "full_instructions": normalization["reference"]}
        now = utc_now()
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """INSERT INTO skills(id,slug,name,description,directory,source_type,source_ref,mode,priority,manifest_json,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,50,?,?,?)""",
                    (skill_id, meta["slug"], meta["name"], meta["description"], str(destination),
                     source_type, source_ref, mode, json.dumps(manifest, ensure_ascii=False), now, now),
                )
        except Exception as exc:
            shutil.rmtree(destination, ignore_errors=True)
            if "UNIQUE" in str(exc).upper():
                raise ConflictError(f"An active skill named {meta['slug']} is already installed") from exc
            raise
        return self.get(skill_id) | {"files": files}

    def install_folder(self, path: str, *, source_type: str = "folder", mode: str = "explicit") -> dict[str, Any]:
        source = Path(path).expanduser().resolve()
        if not source.is_dir() or is_link(source):
            raise ToolError("invalid_source", "Choose a regular local skill folder")
        _validate_tree(source, allow_import_size=True)
        return self._insert(source, source_type=source_type, source_ref=str(source), mode=mode)

    def install_zip(self, encoded: str, *, filename: str = "skill.zip", mode: str = "explicit") -> dict[str, Any]:
        try:
            raw = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ToolError("invalid_archive", "ZIP payload is not valid base64") from exc
        if len(raw) > MAX_ARCHIVE:
            raise ToolError("skill_too_large", "ZIP archive exceeds 10 MB")
        with tempfile.TemporaryDirectory(prefix="skill-zip-", dir=self.root) as temporary:
            archive = Path(temporary) / "upload.zip"
            archive.write_bytes(raw)
            unpacked = Path(temporary) / "unpacked"
            unpacked.mkdir()
            try:
                with zipfile.ZipFile(archive) as bundle:
                    infos = bundle.infolist()
                    if len(infos) > MAX_FILES or sum(item.file_size for item in infos) > MAX_TOTAL:
                        raise ToolError("skill_too_large", "Unpacked skill exceeds 25 MB or 1,000 files")
                    for item in infos:
                        relative = Path(item.filename.replace("\\", "/"))
                        mode_bits = item.external_attr >> 16
                        if relative.is_absolute() or ".." in relative.parts or ":" in item.filename or (mode_bits & 0o170000) == 0o120000:
                            raise ToolError("invalid_archive", "ZIP contains an unsafe path or link")
                    try:
                        bundle.extractall(unpacked)
                    except OSError as exc:
                        raise ToolError("invalid_archive", "ZIP contains a path unsupported on this system") from exc
            except zipfile.BadZipFile as exc:
                raise ToolError("invalid_archive", "The selected file is not a valid ZIP") from exc
            roots = [path.parent for path in unpacked.rglob("SKILL.md")]
            if len(roots) != 1:
                raise ToolError("invalid_archive", "ZIP must contain exactly one SKILL.md")
            return self._insert(roots[0], source_type="zip", source_ref=filename[:240], mode=mode)

    def install_git(self, url: str, *, mode: str = "explicit") -> dict[str, Any]:
        parsed = urlsplit(url)
        if not re.fullmatch(r"https://[^\s]+", url) or len(url) > 1_000 or not parsed.hostname or parsed.username or parsed.password:
            raise ToolError("invalid_source", "Git source must be an HTTPS URL")
        subdirectory = unquote(parsed.fragment).strip().replace("\\", "/")
        relative_subdirectory = Path(subdirectory) if subdirectory else None
        if relative_subdirectory and (relative_subdirectory.is_absolute() or ".." in relative_subdirectory.parts or ":" in subdirectory):
            raise ToolError("invalid_source", "Git skill subdirectory must stay inside the repository")
        clone_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
        with tempfile.TemporaryDirectory(prefix="skill-git-", dir=self.root) as temporary:
            target = Path(temporary) / "repository"
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            clone_arguments = ["git", "clone", "--depth", "1", "--no-recurse-submodules"]
            if relative_subdirectory:
                clone_arguments.extend(["--filter=blob:none", "--sparse"])
            clone_arguments.extend(["--", clone_url, str(target)])
            try:
                result = subprocess.run(clone_arguments, capture_output=True, timeout=60, creationflags=flags)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ToolError("git_failed", "Git clone failed or timed out") from exc
            if result.returncode:
                raise ToolError("git_failed", result.stderr.decode("utf-8", errors="replace")[-2_000:])
            if relative_subdirectory:
                try:
                    result = subprocess.run(
                        ["git", "-C", str(target), "sparse-checkout", "set", "--no-cone", subdirectory],
                        capture_output=True, timeout=30, creationflags=flags,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise ToolError("git_failed", "Git sparse checkout failed or timed out") from exc
                if result.returncode:
                    raise ToolError("git_failed", result.stderr.decode("utf-8", errors="replace")[-2_000:])
            git_dir = target / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir, onerror=_remove_readonly)
            selected = target.joinpath(relative_subdirectory) if relative_subdirectory else target
            if relative_subdirectory and (not selected.is_dir() or is_link(selected)):
                raise ToolError("invalid_source", "Git skill subdirectory does not exist")
            roots = [path.parent for path in selected.rglob("SKILL.md")]
            if relative_subdirectory and (selected / "SKILL.md").is_file():
                roots = [selected]
            if len(roots) != 1:
                raise ToolError("invalid_source", "Git source must resolve to exactly one skill folder")
            return self._insert(roots[0], source_type="git", source_ref=url, mode=mode)

    def list(self, *, deleted: bool = False) -> list[dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT * FROM skills WHERE deleted_at IS " + ("NOT NULL" if deleted else "NULL") + " ORDER BY priority DESC,name"
            ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, skill_id: str, *, include_deleted: bool = False) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM skills WHERE id = ?" + ("" if include_deleted else " AND deleted_at IS NULL"), (skill_id,)).fetchone()
        if not row:
            raise NotFoundError("Skill not found")
        value = self._row(row)
        root = self._skill_root(value)
        meta = _metadata(root)
        value.update({"skill_md": meta["skill_md"], "resources": _validate_tree(root)})
        return value

    def update(self, skill_id: str, *, mode: str | None = None, priority: int | None = None,
               skill_md: str | None = None) -> dict[str, Any]:
        current = self.get(skill_id)
        if mode is not None and mode not in MODES:
            raise ToolError("invalid_mode", "Unknown skill mode")
        if priority is not None and not 0 <= priority <= 100:
            raise ToolError("invalid_priority", "Priority must be from 0 to 100")
        root = self._skill_root(current)
        meta = None
        original: bytes | None = None
        if skill_md is not None:
            self.validate_text(skill_md)
            original = (root / "SKILL.md").read_bytes()
            temporary = root / f".SKILL-{uuid.uuid4().hex}.tmp"
            temporary.write_text(skill_md, encoding="utf-8")
            temporary.replace(root / "SKILL.md")
            meta = _metadata(root)
        fields, values = ["updated_at = ?"], [utc_now()]
        for key, value in (("mode", mode), ("priority", priority)):
            if value is not None:
                fields.append(f"{key} = ?"); values.append(value)
        if meta:
            fields.extend(["slug = ?", "name = ?", "description = ?"])
            values.extend([meta["slug"], meta["name"], meta["description"]])
        values.append(skill_id)
        try:
            with self.database.transaction() as connection:
                connection.execute(f"UPDATE skills SET {', '.join(fields)} WHERE id = ? AND deleted_at IS NULL", values)
        except Exception as exc:
            if original is not None:
                rollback = root / f".SKILL-{uuid.uuid4().hex}.rollback"
                rollback.write_bytes(original)
                rollback.replace(root / "SKILL.md")
            if "UNIQUE" in str(exc).upper():
                raise ConflictError("Another active skill already uses this slug") from exc
            raise
        return self.get(skill_id)

    def trash(self, skill_id: str) -> dict[str, Any]:
        with self.database.transaction() as connection:
            cursor = connection.execute("UPDATE skills SET deleted_at = COALESCE(deleted_at, ?), updated_at = ? WHERE id = ?",
                                        (utc_now(), utc_now(), skill_id))
            if not cursor.rowcount:
                raise NotFoundError("Skill not found")
        return {"id": skill_id, "recoverable": True}

    def restore(self, skill_id: str) -> dict[str, Any]:
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute("UPDATE skills SET deleted_at = NULL, updated_at = ? WHERE id = ?", (utc_now(), skill_id))
                if not cursor.rowcount:
                    raise NotFoundError("Skill not found")
            return self.get(skill_id)
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise ConflictError("An active skill with this slug already exists") from exc
            raise

    def read_resource(self, skill_id: str, path: str, *, selected_ids: set[str] | None = None) -> dict[str, Any]:
        if selected_ids is not None and skill_id not in selected_ids:
            raise ToolError("skill_not_selected", "This skill was not activated for the current turn")
        skill = self.get(skill_id)
        root = self._skill_root(skill)
        raw_path = path.strip().replace("\\", "/")
        relative = Path(raw_path)
        if not raw_path or relative.is_absolute() or ".." in relative.parts or ":" in raw_path:
            raise ToolError("invalid_path", "Skill resource path must stay inside the skill")
        candidate = root.joinpath(relative)
        current = root
        for part in relative.parts:
            current = current / part
            if is_link(current):
                raise ToolError("invalid_path", "Skill resource paths cannot contain links")
        if not candidate.is_file():
            raise ToolError("not_found", "Skill resource not found")
        raw = candidate.read_bytes()
        truncated = len(raw) > MAX_TEXT
        raw = raw[:MAX_TEXT]
        if b"\x00" in raw:
            raise ToolError("binary_resource", "Skill resource is not text")
        return {"skill_id": skill_id, "skill": skill["name"], "path": relative.as_posix(),
                "content": raw.decode("utf-8", errors="replace" if truncated else "strict"), "truncated": truncated}

    def read_full(self, skill_id: str) -> dict[str, Any]:
        skill = self.get(skill_id)
        content = skill["skill_md"]
        return {"id": skill_id, "slug": skill["slug"], "name": skill["name"],
                "description": skill["description"], "content": content,
                "sha256": hashlib.sha256(content.encode()).hexdigest()}

    def script_path(self, skill_id: str, path: str, *, selected_ids: set[str]) -> tuple[dict[str, Any], Path, str]:
        resource = self.read_resource(skill_id, path, selected_ids=selected_ids)
        relative = Path(resource["path"])
        if not relative.parts or relative.parts[0] != "scripts" or relative.suffix.lower() not in {".py", ".js", ".sh"}:
            raise ToolError("invalid_script", "Only .py, .js or .sh files under scripts/ can run")
        skill = self.get(skill_id)
        return skill, self._skill_root(skill), relative.as_posix()

    def match(self, prompt: str) -> dict[str, Any]:
        explicit_slugs = set(re.findall(r"(?:\$|@)([a-z0-9][a-z0-9-]{0,63})\b", prompt.lower()))
        explicit_slugs.update(re.findall(r"/skill\s+([a-z0-9][a-z0-9-]{0,63})\b", prompt.lower()))
        words = {word for word in re.findall(r"[\w-]{3,}", prompt.lower(), re.UNICODE) if word not in STOP}
        candidates, selected = [], []
        for skill in self.list():
            haystack = f"{skill['name']} {skill['slug']} {skill['description']}".lower()
            skill_words = {word for word in re.findall(r"[\w-]{3,}", haystack, re.UNICODE) if word not in STOP}
            overlap = sorted(words & skill_words)
            explicit = skill["slug"] in explicit_slugs
            score = (1_000 if explicit else 100 if skill["mode"] == "always" else 0) + len(overlap) * 10 + skill["priority"] / 100
            reason = "explicit" if explicit else "always" if skill["mode"] == "always" else "description" if overlap else "none"
            activate = skill["mode"] != "off" and (explicit or skill["mode"] == "always" or (skill["mode"] == "auto" and bool(overlap)))
            item = {"id": skill["id"], "slug": skill["slug"], "name": skill["name"], "description": skill["description"],
                    "mode": skill["mode"], "priority": skill["priority"], "score": score, "reason": reason,
                    "matched_terms": overlap, "selected": activate}
            if explicit or overlap or skill["mode"] == "always":
                candidates.append(item)
            if activate:
                selected.append(item)
        selected.sort(key=lambda item: (-item["score"], -item["priority"], item["name"]))
        return {"explicit": sorted(explicit_slugs), "candidates": candidates, "selected": selected[:3]}

    def export_zip(self, skill_id: str) -> tuple[str, bytes]:
        skill = self.get(skill_id)
        root = self._skill_root(skill)
        with tempfile.TemporaryDirectory(prefix="skill-export-", dir=self.root) as temporary:
            target = Path(temporary) / f"{skill['slug']}.zip"
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in walk_files(root):
                    archive.write(path, f"{skill['slug']}/{path.relative_to(root).as_posix()}")
            return target.name, target.read_bytes()

    def _skill_root(self, skill: dict[str, Any]) -> Path:
        root = Path(skill["directory"]).resolve()
        if root.parent != self.root or not root.is_dir() or is_link(root):
            raise ToolError("invalid_skill", "Managed skill directory is unavailable")
        return root

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        value = dict(row)
        value["manifest"] = json.loads(value.pop("manifest_json"))
        value["enabled"] = value["mode"] != "off" and value["deleted_at"] is None
        return value
