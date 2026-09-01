from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import uuid

from backend.sandbox.runtime import DockerSandboxRuntime
from backend.tools.contracts import ToolError


class DocumentRunner:
    """Fixed renderer, offline container, only one job directory writable. No host fallback."""
    def __init__(self, sandbox: DockerSandboxRuntime):
        self.sandbox = sandbox

    def arguments(self, job: Path, name: str) -> list[str]:
        return ["run", "--rm", "--pull", "never", "--init", "--name", name,
                "--label", f"com.symphony.instance={self.sandbox.instance_id}",
                "--user", f"{os.getuid()}:{os.getgid()}" if os.name != "nt" and os.getuid() != 0 else "10001:10001", "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--memory", "1g", "--cpus", "1.5", "--pids-limit", "128",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m", "--env", "HOME=/tmp",
                "--env", "PYTHONPATH=/opt", "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--mount", f"type=bind,source={job},target=/job",
                "--mount", f"type=bind,source={Path(__file__).resolve().parent},target=/opt/artifacts,readonly",
                "--workdir", "/job", self.sandbox.image, "python", "-m", "artifacts.worker", "/job"]

    async def render(self, job: Path, on_output=None):
        await self.sandbox.recover_orphans()
        code, version = await self.sandbox._docker_control("image", "inspect", self.sandbox.image, "--format", '{{index .Config.Labels "com.symphony.runtime.version"}}')
        if code or version.strip() not in {"5.0", "6.0"}:
            raise ToolError("document_runtime_outdated", "Document runtime 5.0 or 6.0 is not ready. Finish START.bat or scripts/build-runtime.ps1, then retry; do not install dependencies through chat tools.")
        name = "symphony-document-" + uuid.uuid4().hex
        try:
            process = await asyncio.create_subprocess_exec(self.sandbox.docker_binary, *self.arguments(job, name),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except OSError as error:
            raise ToolError("document_runtime_unavailable", "Start Docker and rebuild the Symphony runtime with START.bat") from error
        try:
            stdout, stderr, code = await asyncio.wait_for(asyncio.gather(
                self.sandbox._read_limited(process.stdout, "stdout", on_output),
                self.sandbox._read_limited(process.stderr, "stderr", on_output), process.wait()), timeout=150)
            if code:
                message = "Trusted renderer failed"
                try: message = str(json.loads(stdout[0]).get("error", message))[:2000]
                except (ValueError, AttributeError): pass
                raise ToolError("document_render_failed", message, details={"stdout": stdout[0], "stderr": stderr[0]})
        except (asyncio.CancelledError, TimeoutError):
            await self.sandbox._force_remove(name, process)
            raise
