from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

from backend.tools.contracts import ToolError


class IsolatedExtractor:
    """No network, no project mount, one read-only copied input and trusted parser."""
    def __init__(self, sandbox):
        self.sandbox = sandbox

    def arguments(self, source: Path, name: str):
        return ["run", "--rm", "--pull", "never", "--init", "--name", name,
                "--label", f"com.symphony.instance={self.sandbox.instance_id}",
                "--user", "10001:10001", "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "512m",
                "--cpus", "1", "--pids-limit", "32", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
                "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--mount", f"type=bind,source={source},target=/input{source.suffix},readonly",
                "--mount", f"type=bind,source={Path(__file__).with_name('extraction_worker.py')},target=/parser.py,readonly",
                self.sandbox.image, "python", "/parser.py", f"/input{source.suffix}"]

    async def extract(self, raw: bytes, suffix: str) -> str:
        await self.sandbox.recover_orphans()
        name = "symphony-extract-" + uuid.uuid4().hex
        with tempfile.TemporaryDirectory(prefix="symphony-extract-") as directory:
            source = Path(directory) / ("source" + suffix)
            source.write_bytes(raw)
            source.chmod(0o644)
            try:
                process = await asyncio.create_subprocess_exec(self.sandbox.docker_binary, *self.arguments(source, name),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            except OSError as exc:
                raise ToolError("index_runtime_unavailable", "Для PDF/Office нужен Docker. Запустите START.bat") from exc
            async def read(stream, limit):
                value = bytearray()
                while chunk := await stream.read(65536):
                    value.extend(chunk)
                    if len(value) > limit:
                        raise ToolError("extraction_output_limit", "Parser output exceeded its limit")
                return value.decode("utf-8", errors="replace")
            try:
                async with asyncio.timeout(60):
                    stdout, stderr, code = await asyncio.gather(read(process.stdout, 12_100_000), read(process.stderr, 16000), process.wait())
                try:
                    result = json.loads(stdout)
                except ValueError as exc:
                    raise ToolError("index_runtime_failed", "Не удалось разобрать файл в Docker. Проверьте START.bat", details={"stderr": stderr}) from exc
                if code or "text" not in result:
                    raise ToolError("index_failed", result.get("error", "Document extraction failed"))
                return result["text"]
            except BaseException:
                await self.sandbox._force_remove(name, process)
                raise
