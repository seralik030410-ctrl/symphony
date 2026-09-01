import io
import json
import zipfile
from pathlib import Path

import pytest

from backend.agent.memory import MemoryStore
from backend.agent.retrieval import FileIndex
from backend.agent.extraction import IsolatedExtractor
from backend.agent.extraction_worker import extract
from backend.models.tokens import estimate_tokens
from backend.models.base import ProviderError


@pytest.mark.parametrize("value", ["not JSON", "{}", '{"facts":"a"}', json.dumps({"facts": ["a"*301], "decisions": [], "open_tasks": [], "artifact_index": []}), json.dumps({"facts": [], "decisions": [], "open_tasks": [], "artifact_index": [], "source_message_ids": ["foreign"]})])
def test_invalid_memory_cannot_replace_history(value):
    with pytest.raises(ProviderError) as error:
        MemoryStore.validate(value)
    assert error.value.code == "invalid_memory"


def test_multimodal_estimator_does_not_count_base64():
    ollama = [{"role": "user", "content": "hello", "images": ["x" * 100000]}]
    api = [{"role": "user", "content": [{"type": "text", "text": "hello"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "x" * 100000}}]}]
    assert estimate_tokens(ollama) == estimate_tokens(api) == 2054


def test_chunks_cover_entire_two_million_character_source():
    text = ("a" * 1200 + "\n") * 1665
    chunks = FileIndex._chunks(text)
    assert len(chunks) > 800
    assert chunks[-1][1] == len(text.strip())
    for start, end, content in chunks:
        assert text[start:end] == content
    assert all(chunks[index+1][0] <= chunks[index][1] for index in range(len(chunks)-1))


def test_expanded_office_archive_limit(tmp_path):
    path = tmp_path / "oversized.docx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "a" * 31_000_000)
    with pytest.raises(ValueError, match="oversized"):
        extract(path)


def test_extraction_mounts_no_project_or_secrets(app, tmp_path):
    args = IsolatedExtractor(app.state.runtime.sandbox).arguments(tmp_path / "input.pdf", "symphony-extract-test")
    assert args[args.index("--network")+1] == "none"
    assert "--read-only" in args and "--cap-drop" in args and "--pids-limit" in args
    mounts = [args[index+1] for index, item in enumerate(args) if item == "--mount"]
    assert len(mounts) == 2 and all(item.endswith(",readonly") for item in mounts)
    assert not any("workspace" in item or "docker.sock" in item for item in mounts)
