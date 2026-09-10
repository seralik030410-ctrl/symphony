from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest
from PIL import Image

from backend.media.assets import MediaAssetStore
from backend.media.jobs import MediaJobStore
from backend.media.providers.comfyui import (
    ComfyUIConnection,
    ComfyUIConnector,
    validate_comfyui_url,
    validate_output_descriptor,
    validate_proxy_path,
)
from backend.models.base import ModelCapabilities
from backend.storage.repository import ConflictError, NotFoundError
from backend.tools.contracts import ToolError
from backend.vision.contracts import FrameProvenance
from backend.vision.limits import VisionLimitError, validate_image_attachments


def png_bytes(size: tuple[int, int] = (32, 20)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "#1954a6").save(output, "PNG")
    return output.getvalue()


def test_media_assets_validate_signature_dedupe_and_chat_scope(app, tmp_path: Path):
    runtime = app.state.runtime
    first = runtime.repository.create_session(title="one", provider="ollama", model="test-model", system_prompt="", context_window=4096, max_output=128)
    second = runtime.repository.create_session(title="two", provider="ollama", model="test-model", system_prompt="", context_window=4096, max_output=128)
    store = MediaAssetStore(runtime.database, tmp_path / "media")
    asset, created = store.put(first["id"], png_bytes(), filename="frame.png", mime_type="image/png", source="camera", provenance={"source": "camera"})
    duplicate, created_again = store.put(first["id"], png_bytes(), filename="renamed.png", mime_type="image/png", source="file")
    assert created and not created_again and duplicate["id"] == asset["id"]
    assert store.list(second["id"]) == []
    with pytest.raises(ToolError, match="does not match"):
        store.put(first["id"], b"not png", filename="bad.png", mime_type="image/png", source="file")
    with pytest.raises(NotFoundError):
        store.get(second["id"], asset["id"])


def test_media_assets_integrity_and_recoverable_trash(app, tmp_path: Path):
    runtime = app.state.runtime
    session = runtime.repository.create_session(title="media", provider="ollama", model="test-model", system_prompt="", context_window=4096, max_output=128)
    store = MediaAssetStore(runtime.database, tmp_path / "media")
    asset, _ = store.put(session["id"], png_bytes(), filename="frame.png", mime_type="image/png", source="file")
    path, _ = store.verified_file(session["id"], asset["id"])
    path.write_bytes(b"changed")
    with pytest.raises(ToolError) as error:
        store.verified_file(session["id"], asset["id"])
    assert error.value.code == "media_integrity_error"
    store.trash(session["id"], asset["id"])
    assert store.list(session["id"]) == []
    assert store.restore(session["id"], asset["id"])["id"] == asset["id"]


def test_media_jobs_isolate_scope_cancel_retry_and_monotonic_progress(app):
    runtime = app.state.runtime
    one = runtime.repository.create_session(title="one", provider="ollama", model="test-model", system_prompt="", context_window=4096, max_output=128)
    two = runtime.repository.create_session(title="two", provider="ollama", model="test-model", system_prompt="", context_window=4096, max_output=128)
    jobs = MediaJobStore(runtime.database, runtime.repository)
    job = jobs.create(one["id"], "media.comfyui.image", {"workflow": {"1": {}}})
    with pytest.raises(NotFoundError):
        jobs.get(two["id"], job["id"])
    assert jobs.claim_next()["status"] == "preparing"
    jobs.transition(one["id"], job["id"], "running")
    jobs.progress(one["id"], job["id"], 0.8)
    assert jobs.progress(one["id"], job["id"], 0.2)["progress"] == 0.8
    failed = jobs.transition(one["id"], job["id"], "failed", error_code="provider")
    retry = jobs.retry(one["id"], failed["id"])
    assert retry["attempt"] == 2 and retry["retry_of_job_id"] == failed["id"]
    cancelled = jobs.cancel(one["id"], retry["id"])
    assert cancelled["status"] == "cancelled"
    sequences = [event["sequence"] for event in jobs.events(one["id"], failed["id"])]
    assert sequences == list(range(1, len(sequences) + 1))


def test_media_job_recovery_requeues_running_and_cancels_requested(app):
    runtime = app.state.runtime
    session = runtime.repository.create_session(title="recover", provider="ollama", model="test-model", system_prompt="", context_window=4096, max_output=128)
    jobs = MediaJobStore(runtime.database, runtime.repository)
    running = jobs.create(session["id"], "media.comfyui.image", {"workflow": {"1": {}}})
    jobs.claim_next(); jobs.transition(session["id"], running["id"], "running")
    pending = jobs.create(session["id"], "media.comfyui.image", {"workflow": {"2": {}}})
    jobs.claim_next(); jobs.transition(session["id"], pending["id"], "running"); jobs.cancel(session["id"], pending["id"])
    assert jobs.recover() == 2
    assert jobs.get(session["id"], running["id"])["status"] == "queued"
    assert jobs.get(session["id"], pending["id"])["status"] == "cancelled"


def test_voice_state_machine_and_frame_provenance_bounds(app):
    runtime = app.state.runtime
    session = runtime.repository.create_session(title="voice", provider="ollama", model="test-model", system_prompt="", context_window=4096, max_output=128)
    voice = runtime.voice.store.create(session["id"])
    voice = runtime.voice.store.transition(session["id"], voice["id"], "listening")
    voice = runtime.voice.store.transition(session["id"], voice["id"], "transcribing")
    assert voice["status"] == "transcribing"
    with pytest.raises(ConflictError, match="transcribing to speaking"):
        runtime.voice.store.transition(session["id"], voice["id"], "speaking")
    provenance = FrameProvenance.from_mapping({"source": "camera", "reason": "change", "sequence": 3, "change_score": 0.25, "device_label": "  webcam  "})
    assert provenance.as_dict()["device_label"] == "webcam" and provenance.sequence == 3


def test_vision_limits_select_only_vision_and_reject_frames_dimensions_and_tokens():
    capabilities = ModelCapabilities(max_vision_frames=1, max_image_bytes=1000, max_image_width=100, max_image_height=100, max_image_tokens=2048, max_vision_tokens=2048)
    ocr = {"mime_type": "image/png", "image_mode": "ocr", "width": 10, "height": 10, "size": 20, "filename": "ocr.png"}
    frame = {"mime_type": "image/png", "image_mode": "vision", "width": 64, "height": 64, "size": 20, "filename": "frame.png"}
    selected, total = validate_image_attachments([ocr, frame], capabilities)
    assert selected == [frame] and total == 255 and frame["estimated_tokens"] == 255
    with pytest.raises(VisionLimitError, match="at most"):
        validate_image_attachments([frame, dict(frame, filename="two.png")], capabilities)
    with pytest.raises(VisionLimitError, match="dimensions"):
        validate_image_attachments([dict(frame, width=0)], capabilities)


def test_comfyui_url_paths_outputs_and_private_network_policy():
    assert validate_comfyui_url("HTTPS://Example.COM/") == "https://example.com"
    with pytest.raises(ToolError) as error:
        validate_comfyui_url("http://127.0.0.1:8188")
    assert error.value.code == "comfyui_private_network_denied"
    assert validate_comfyui_url("http://127.0.0.1:8188", allow_private_network=True) == "http://127.0.0.1:8188"
    with pytest.raises(ToolError):
        validate_proxy_path("/../secret")
    assert validate_proxy_path("/view/a b.png") == "view/a%20b.png"
    assert validate_output_descriptor({"filename": "x.png", "subfolder": "nested", "type": "output"})["subfolder"] == "nested"
    with pytest.raises(ToolError):
        validate_output_descriptor({"filename": "../x.png"})


@pytest.mark.asyncio
async def test_comfyui_transport_validates_workflow_output_and_cancel_without_network():
    calls = []
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/prompt": return httpx.Response(200, json={"prompt_id": "p1"})
        if request.url.path == "/view": return httpx.Response(200, headers={"content-type": "image/png"}, content=png_bytes())
        return httpx.Response(200, json={})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    connector = ComfyUIConnector(ComfyUIConnection("http://127.0.0.1:8188", allow_private_network=True), client=client)
    assert await connector.queue_prompt({"1": {}}) == "p1"
    assert (await connector.fetch_output({"filename": "x.png"}))[2] == "image/png"
    await connector.cancel("p1")
    assert ("POST", "/queue") in calls and ("POST", "/interrupt") in calls
    with pytest.raises(ToolError, match="non-empty"):
        await connector.queue_prompt({})
    await client.aclose()


@pytest.mark.asyncio
async def test_comfyui_proxy_routes_forward_to_configured_origin_and_filter_headers(app, client):
    calls: list[dict[str, object]] = []

    class Connector:
        origin = "http://approved-comfy.test"

        async def proxy(self, method, path, *, query, body, headers):
            calls.append({"method": method, "path": path, "query": query, "body": body, "headers": headers})
            return httpx.Response(
                206,
                content=b"upstream-body",
                headers={
                    "content-type": "application/octet-stream",
                    "etag": "test-etag",
                    "connection": "keep-alive",
                    "set-cookie": "private=secret",
                    "server": "hidden",
                },
            )

        async def close(self):
            return None

    runtime = app.state.runtime
    assert (await client.get("/api/comfyui/proxy/view/file.png")).status_code == 422
    runtime.media.comfyui = Connector()

    response = await client.get(
        "/api/comfyui/proxy/view/file.png?preview=1",
        headers={"accept": "image/png", "authorization": "must-not-forward"},
    )
    assert response.status_code == 206 and response.content == b"upstream-body"
    assert response.headers["etag"] == "test-etag"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "connection" not in response.headers and "set-cookie" not in response.headers and "server" not in response.headers
    assert calls[0] == {
        "method": "GET",
        "path": "view/file.png",
        "query": "preview=1",
        "body": None,
        "headers": {"accept": "image/png", "user-agent": "python-httpx/0.28.1"},
    }

    posted = await client.post(
        "/api/comfyui/proxy/prompt",
        content=b'{"prompt":{}}',
        headers={"content-type": "application/json"},
    )
    assert posted.status_code == 206 and calls[1]["method"] == "POST" and calls[1]["body"] == b'{"prompt":{}}'
    headed = await client.head("/api/comfyui/proxy/system_stats")
    assert headed.status_code == 206 and headed.content == b"" and calls[2]["method"] == "HEAD"
