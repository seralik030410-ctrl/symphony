import base64
import io
import shutil
import stat
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.skills.store import SkillStore
from backend.storage.database import Database
from backend.storage.repository import ConflictError, NotFoundError
from backend.tools.contracts import ToolError


def make_skill(root, name="Site audit", description="Review a website accessibility layout"):
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n# {name}\nRead `references/check.md`.\n", encoding="utf-8")
    (root / "references").mkdir()
    (root / "references" / "check.md").write_text("keyboard and contrast", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "check.py").write_text("print('ok')", encoding="utf-8")
    return root


def store(tmp_path):
    database = Database(tmp_path / "skills.db")
    database.initialize()
    return SkillStore(database, tmp_path / "managed")


def test_metadata_index_modes_progressive_read_and_soft_delete(tmp_path):
    skills = store(tmp_path)
    installed = skills.install_folder(str(make_skill(tmp_path / "source")), mode="explicit")
    summary = skills.list()[0]
    assert "skill_md" not in summary and summary["slug"] == "site-audit"
    assert not skills.match("review website accessibility")["selected"]
    assert skills.match("Use $site-audit please")["selected"][0]["reason"] == "explicit"
    skills.update(installed["id"], mode="auto", priority=88)
    match = skills.match("review website accessibility")
    assert match["selected"][0]["priority"] == 88
    assert skills.read_resource(installed["id"], "references/check.md", selected_ids={installed["id"]})["content"] == "keyboard and contrast"
    with pytest.raises(ToolError, match="not activated"):
        skills.read_resource(installed["id"], "references/check.md", selected_ids=set())
    skills.trash(installed["id"])
    assert skills.list() == [] and skills.list(deleted=True)[0]["id"] == installed["id"]
    with pytest.raises(NotFoundError):
        skills.get(installed["id"])
    assert skills.restore(installed["id"])["id"] == installed["id"]


def test_zip_export_edit_validation_and_security(tmp_path):
    skills = store(tmp_path)
    source = make_skill(tmp_path / "zip-source")
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        for path in source.rglob("*"):
            if path.is_file(): archive.write(path, f"wrapper/{path.relative_to(source).as_posix()}")
    installed = skills.install_zip(base64.b64encode(payload.getvalue()).decode(), filename="audit.zip")
    name, exported = skills.export_zip(installed["id"])
    assert name == "site-audit.zip" and zipfile.ZipFile(io.BytesIO(exported)).testzip() is None
    changed = installed["skill_md"].replace("Site audit", "Site quality")
    assert skills.update(installed["id"], skill_md=changed)["slug"] == "site-quality"
    assert SkillStore.validate_text(changed)["valid"]
    with pytest.raises(ToolError):
        skills.read_resource(installed["id"], "../secret")
    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../SKILL.md", changed)
    with pytest.raises(ToolError, match="unsafe"):
        skills.install_zip(base64.b64encode(unsafe.getvalue()).decode())


def test_duplicate_active_slug_and_disabled_explicit_skill(tmp_path):
    skills = store(tmp_path)
    first = skills.install_folder(str(make_skill(tmp_path / "one")))
    with pytest.raises(ConflictError):
        skills.install_folder(str(make_skill(tmp_path / "two")))
    skills.update(first["id"], mode="off")
    match = skills.match("$site-audit")
    assert match["candidates"][0]["selected"] is False and match["selected"] == []


def test_conflicting_edit_restores_original_skill_file(tmp_path):
    skills = store(tmp_path)
    first = skills.install_folder(str(make_skill(tmp_path / "one")))
    second = skills.install_folder(str(make_skill(tmp_path / "two", name="Other skill")))
    original = second["skill_md"]
    with pytest.raises(ConflictError):
        skills.update(second["id"], skill_md=original.replace("Other skill", "Site audit"))
    assert skills.get(second["id"])["skill_md"] == original
    assert skills.get(first["id"])["slug"] == "site-audit"


def test_skill_md_is_bounded_for_context_safety(tmp_path):
    skills = store(tmp_path)
    too_large = "---\nname: Huge\ndescription: Huge workflow\n---\n" + ("instruction\n" * 800)
    with pytest.raises(ToolError, match="8 KB"):
        skills.validate_text(too_large)


def test_folded_frontmatter_description_is_parsed(tmp_path):
    skills = store(tmp_path)
    result = skills.validate_text(
        "---\nname: Folded workflow\ndescription: >\n  First part of the description\n  continues on the next line.\n---\n# Folded workflow\n"
    )
    assert result["description"] == "First part of the description continues on the next line."


def test_long_import_is_normalized_into_progressive_reference(tmp_path):
    skills = store(tmp_path)
    source = tmp_path / "long-skill"
    source.mkdir()
    original = "---\nname: Long workflow\ndescription: A detailed imported workflow\n---\n" + ("important instruction\n" * 500)
    (source / "SKILL.md").write_text(original, encoding="utf-8")
    installed = skills.install_folder(str(source))
    assert len(installed["skill_md"].encode()) <= 8_000
    reference = installed["manifest"]["_symphony"]["full_instructions"]
    assert reference == "references/symphony-full-skill.md"
    assert skills.read_resource(installed["id"], reference)["content"].replace("\r\n", "\n") == original


def test_git_url_subdirectory_selects_one_skill(tmp_path, monkeypatch):
    skills = store(tmp_path)
    repository = tmp_path / "remote"
    make_skill(repository / "packages" / "chosen", name="Git chosen")
    make_skill(repository / "packages" / "other", name="Git other")

    def clone(arguments, **_kwargs):
        if arguments[1] != "clone":
            assert arguments[3:6] == ["sparse-checkout", "set", "--no-cone"]
            assert arguments[-1] == "packages/chosen"
            return SimpleNamespace(returncode=0, stderr=b"")
        assert arguments[-2] == "https://github.com/example/skills.git"
        assert "--filter=blob:none" in arguments
        assert "--sparse" in arguments
        shutil.copytree(repository, arguments[-1])
        pack = Path(arguments[-1]) / ".git" / "objects" / "pack" / "pack.idx"
        pack.parent.mkdir(parents=True)
        pack.write_bytes(b"git pack index")
        pack.chmod(stat.S_IREAD)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("backend.skills.store.subprocess.run", clone)
    installed = skills.install_git("https://github.com/example/skills.git#packages/chosen")
    assert installed["slug"] == "git-chosen"
    assert installed["source_ref"].endswith("#packages/chosen")
