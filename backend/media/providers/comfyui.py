"""A constrained ComfyUI transport and optional local process manager.

ComfyUI is deliberately treated as an untrusted service.  The connector has a
single validated origin and only exposes known API calls; browser embedding is
served through the same restriction by ``backend.api.comfyui``.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import socket
import uuid
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

import httpx

from backend.tools.contracts import ToolError


MAX_OUTPUT_BYTES = 100_000_000
SAFE_PROXY_METHODS = {"GET", "HEAD", "POST"}
HOP_BY_HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"}


def _is_private_address(hostname: str) -> bool:
    if hostname.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        address = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return False
    return bool(address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified)


def _resolves_to_private(hostname: str) -> bool:
    """Best-effort DNS guard for endpoints supplied by the user.

    A lookup failure is left to the explicit health check; treating it as a
    private address would make offline configuration impossible.
    """
    if _is_private_address(hostname):
        return True
    try:
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    return any(_is_private_address(item[4][0]) for item in addresses if item[4])


def validate_comfyui_url(value: str, *, allow_private_network: bool = False) -> str:
    """Normalize an HTTP(S) base URL and reject credential/path confusion."""
    if not isinstance(value, str) or len(value) > 2_000:
        raise ToolError("invalid_comfyui_url", "ComfyUI URL is invalid")
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ToolError("invalid_comfyui_url", "ComfyUI URL must be an HTTP(S) origin without credentials, query or fragment")
    if parsed.path not in {"", "/"}:
        raise ToolError("invalid_comfyui_url", "ComfyUI URL must not include a path")
    host = parsed.hostname.rstrip(".").lower()
    if not allow_private_network and _resolves_to_private(host):
        raise ToolError("comfyui_private_network_denied", "Private-network ComfyUI endpoints require explicit permission")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ToolError("invalid_comfyui_url", "ComfyUI URL has an invalid port")
    display_host = f"[{host}]" if ":" in host else host
    netloc = display_host if parsed.port is None else f"{display_host}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, "", "", ""))


def validate_proxy_path(path: str) -> str:
    if not isinstance(path, str) or len(path) > 2_000 or "\\" in path or "\x00" in path:
        raise ToolError("invalid_comfyui_path", "ComfyUI proxy path is invalid")
    normalized = path.lstrip("/")
    if not normalized:
        return ""
    parsed = PurePosixPath(normalized)
    if parsed.is_absolute() or ".." in parsed.parts or any(part in {"", "."} for part in parsed.parts):
        raise ToolError("invalid_comfyui_path", "ComfyUI proxy path escapes its allowed origin")
    return "/".join(quote(part, safe="@:+,=~!$&'()") for part in parsed.parts)


def validate_output_descriptor(value: dict[str, Any]) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ToolError("invalid_comfyui_output", "ComfyUI output descriptor must be an object")
    filename = value.get("filename")
    subfolder = value.get("subfolder", "")
    output_type = value.get("type", "output")
    if not isinstance(filename, str) or not filename or len(filename) > 240 or "/" in filename or "\\" in filename or ".." in filename or "\x00" in filename:
        raise ToolError("invalid_comfyui_output", "ComfyUI output filename is invalid")
    if not isinstance(subfolder, str) or len(subfolder) > 500 or "\\" in subfolder or "\x00" in subfolder:
        raise ToolError("invalid_comfyui_output", "ComfyUI output subfolder is invalid")
    parts = PurePosixPath(subfolder).parts if subfolder else ()
    if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(subfolder).is_absolute():
        raise ToolError("invalid_comfyui_output", "ComfyUI output subfolder is invalid")
    if output_type != "output":
        raise ToolError("invalid_comfyui_output", "Only finished ComfyUI outputs may be fetched")
    return {"filename": filename, "subfolder": "/".join(parts), "type": "output"}


def _mime_from_response(headers: httpx.Headers, filename: str) -> str:
    value = headers.get("content-type", "").split(";", 1)[0].lower()
    allowed = {"image/png", "image/jpeg", "image/webp", "image/gif", "video/mp4", "video/webm"}
    if value in allowed:
        return value
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif", "mp4": "video/mp4", "webm": "video/webm"}.get(suffix, "")


@dataclass(slots=True)
class ComfyUIConnection:
    base_url: str
    allow_private_network: bool = False
    timeout_seconds: float = 120.0


class ComfyUIConnector:
    def __init__(self, connection: ComfyUIConnection | str, *, allow_private_network: bool = False, timeout_seconds: float = 120.0,
                 client: httpx.AsyncClient | None = None) -> None:
        if isinstance(connection, str):
            connection = ComfyUIConnection(connection, allow_private_network, timeout_seconds)
        self.connection = ComfyUIConnection(
            validate_comfyui_url(connection.base_url, allow_private_network=connection.allow_private_network),
            connection.allow_private_network,
            max(1.0, min(float(connection.timeout_seconds), 3_600.0)),
        )
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(self.connection.timeout_seconds), follow_redirects=False)
        self._owns_client = client is None

    @property
    def origin(self) -> str:
        return self.connection.base_url

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _url(self, path: str, params: dict[str, str] | None = None) -> str:
        safe = validate_proxy_path(path)
        return f"{self.origin}/{safe}" + (f"?{urlencode(params)}" if params else "")

    async def health(self) -> dict[str, Any]:
        try:
            response = await self._client.get(self._url("system_stats"), headers={"Accept": "application/json"})
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("not an object")
            return {"ready": True, "origin": self.origin, "system_stats": body}
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolError("comfyui_unavailable", "ComfyUI connection check failed") from exc

    async def queue_prompt(self, workflow: dict[str, Any], *, client_id: str | None = None, extra_data: dict[str, Any] | None = None) -> str:
        if not isinstance(workflow, dict) or not workflow:
            raise ToolError("invalid_workflow", "ComfyUI workflow must be a non-empty object")
        if len(json.dumps(workflow, ensure_ascii=False).encode("utf-8")) > 512_000:
            raise ToolError("invalid_workflow", "ComfyUI workflow is too large")
        payload: dict[str, Any] = {"prompt": workflow, "client_id": client_id or uuid.uuid4().hex}
        if extra_data:
            payload["extra_data"] = extra_data
        try:
            response = await self._client.post(self._url("prompt"), json=payload)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolError("comfyui_queue_failed", "ComfyUI could not queue this workflow") from exc
        prompt_id = body.get("prompt_id") if isinstance(body, dict) else None
        if not isinstance(prompt_id, str) or not prompt_id or len(prompt_id) > 200:
            error = body.get("error", {}).get("message") if isinstance(body, dict) and isinstance(body.get("error"), dict) else None
            raise ToolError("comfyui_queue_rejected", str(error or "ComfyUI rejected this workflow")[:500])
        return prompt_id

    async def history(self, prompt_id: str) -> dict[str, Any] | None:
        if not isinstance(prompt_id, str) or not prompt_id or len(prompt_id) > 200:
            raise ToolError("invalid_comfyui_prompt", "ComfyUI prompt id is invalid")
        try:
            response = await self._client.get(self._url(f"history/{quote(prompt_id, safe='')}", None), headers={"Accept": "application/json"})
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolError("comfyui_history_failed", "ComfyUI history could not be read") from exc
        if not isinstance(body, dict):
            raise ToolError("comfyui_history_failed", "ComfyUI returned an invalid history response")
        item = body.get(prompt_id)
        return item if isinstance(item, dict) else None

    async def queue_state(self, prompt_id: str) -> str:
        try:
            response = await self._client.get(self._url("queue"), headers={"Accept": "application/json"})
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolError("comfyui_queue_failed", "ComfyUI queue could not be read") from exc
        if not isinstance(body, dict):
            return "unknown"
        for key, state in (("queue_running", "running"), ("queue_pending", "queued")):
            entries = body.get(key, [])
            if isinstance(entries, list) and any(isinstance(entry, (list, tuple)) and prompt_id in entry for entry in entries):
                return state
        return "unknown"

    async def cancel(self, prompt_id: str) -> None:
        if not isinstance(prompt_id, str) or not prompt_id or len(prompt_id) > 200:
            raise ToolError("invalid_comfyui_prompt", "ComfyUI prompt id is invalid")
        try:
            # Removing from the pending queue is safe and repeatable.  The
            # interrupt endpoint additionally asks ComfyUI to stop a running job.
            response = await self._client.post(self._url("queue"), json={"delete": [prompt_id]})
            if response.status_code >= 500:
                response.raise_for_status()
            await self._client.post(self._url("interrupt"), json={})
        except httpx.HTTPError as exc:
            raise ToolError("comfyui_cancel_failed", "ComfyUI cancellation could not be requested") from exc

    @staticmethod
    def outputs(history: dict[str, Any] | None) -> list[dict[str, str]]:
        if not history:
            return []
        result: list[dict[str, str]] = []
        outputs = history.get("outputs")
        if not isinstance(outputs, dict):
            return result
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for family in ("images", "gifs"):
                items = node_output.get(family, [])
                if isinstance(items, list):
                    for value in items:
                        try:
                            result.append(validate_output_descriptor(value))
                        except ToolError:
                            continue
        return result

    async def fetch_output(self, descriptor: dict[str, Any]) -> tuple[bytes, str, str]:
        output = validate_output_descriptor(descriptor)
        try:
            async with self._client.stream("GET", self._url("view", output)) as response:
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length and int(length) > MAX_OUTPUT_BYTES:
                    raise ToolError("comfyui_output_too_large", "ComfyUI output exceeds the 100 MB limit")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_OUTPUT_BYTES:
                        raise ToolError("comfyui_output_too_large", "ComfyUI output exceeds the 100 MB limit")
                mime_type = _mime_from_response(response.headers, output["filename"])
        except ToolError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolError("comfyui_output_fetch_failed", "ComfyUI output could not be downloaded") from exc
        if not mime_type:
            raise ToolError("invalid_comfyui_output", "ComfyUI returned an unsupported output type")
        return bytes(data), output["filename"], mime_type

    async def proxy(self, method: str, path: str, *, query: str = "", body: bytes | None = None,
                    headers: dict[str, str] | None = None) -> httpx.Response:
        if method.upper() not in SAFE_PROXY_METHODS:
            raise ToolError("invalid_comfyui_proxy", "ComfyUI proxy method is not allowed")
        safe_path = validate_proxy_path(path)
        if len(query) > 4_000 or "\x00" in query:
            raise ToolError("invalid_comfyui_proxy", "ComfyUI proxy query is invalid")
        forwarded = {key: value for key, value in (headers or {}).items() if key.lower() not in HOP_BY_HOP_HEADERS | {"host", "cookie", "authorization"}}
        forwarded["Host"] = urlsplit(self.origin).netloc
        try:
            response = await self._client.request(method.upper(), f"{self.origin}/{safe_path}" + (f"?{query}" if query else ""), content=body, headers=forwarded)
            return response
        except httpx.HTTPError as exc:
            raise ToolError("comfyui_proxy_failed", "ComfyUI Studio is unavailable") from exc


class ComfyUIProcessManager:
    """Optional lifecycle owner.  It never starts a shell or accepts UI input."""

    def __init__(self, command: Iterable[str] | None = None, *, cwd: str | None = None,
                 environment: dict[str, str] | None = None) -> None:
        self.command = tuple(command or ())
        self.cwd = cwd
        self.environment = dict(environment or {})
        self._process: asyncio.subprocess.Process | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> bool:
        if self.running:
            return False
        if not self.command or not all(isinstance(part, str) and part and "\x00" not in part for part in self.command):
            raise ToolError("invalid_comfyui_command", "Managed ComfyUI command is not configured")
        environment = {**os.environ, **self.environment}
        self._process = await asyncio.create_subprocess_exec(*self.command, cwd=self.cwd, env=environment,
                                                               stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                                                               stderr=asyncio.subprocess.DEVNULL)
        return True

    async def stop(self, *, timeout: float = 10.0) -> bool:
        process = self._process
        if not process or process.returncode is not None:
            return False
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=max(0.1, timeout))
        except TimeoutError:
            process.kill()
            await process.wait()
        return True
