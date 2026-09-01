from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from backend.tools.contracts import ToolError
from backend.tools.workspace import WorkspaceManager, is_link, walk_files


@dataclass(slots=True)
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    changed_files: list[str] = field(default_factory=list)
    output_truncated: bool = False


class DockerSandboxRuntime:
    """Runs untrusted commands in Docker. There is deliberately no host fallback."""

    def __init__(
        self,
        workspaces: WorkspaceManager,
        *,
        image: str,
        memory: str = "768m",
        cpus: float = 1.5,
        pids_limit: int = 256,
        output_limit: int = 100_000,
        docker_binary: str = "docker",
    ) -> None:
        self.workspaces = workspaces
        self.image = image
        self.memory = memory
        self.cpus = cpus
        self.pids_limit = pids_limit
        self.output_limit = output_limit
        self.docker_binary = docker_binary
        self._containers: dict[str, str] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self.instance_id = hashlib.sha256(str(workspaces.root).encode()).hexdigest()[:24]
        self._recovery_done = False
        self._recovery_lock = asyncio.Lock()

    async def recover_orphans(self) -> None:
        """One backend process per workspace root. Only remove our labelled containers."""
        async with self._recovery_lock:
            if self._recovery_done:
                return
            code, output = await self._docker_control(
                "ps", "-aq", "--filter", f"label=com.symphony.instance={self.instance_id}",
            )
            if code != 0:
                raise ToolError("sandbox_unavailable", "Docker is not ready; chat remains available")
            ids = output.split()
            if ids:
                code, _ = await self._docker_control("rm", "--force", *ids)
                if code:
                    raise ToolError("sandbox_cleanup_failed", "Could not stop abandoned sandbox containers")
            self._recovery_done = True

    async def _docker_control(self, *arguments: str) -> tuple[int, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                self.docker_binary, *arguments, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except OSError:
            return -1, "Docker CLI is not available"
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        except (TimeoutError, asyncio.CancelledError):
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        return process.returncode, (stdout if process.returncode == 0 else stderr).decode("utf-8", errors="replace")

    async def health(self) -> tuple[bool, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                self.docker_binary,
                "image",
                "inspect",
                self.image,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, OSError):
            return False, "Docker CLI is not installed"
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
            return False, "Docker daemon is not responding"
        if process.returncode == 0:
            return True, f"Sandbox image {self.image} is ready"
        message = stderr.decode("utf-8", errors="replace").strip()
        if "daemon" in message.lower() or "pipe" in message.lower():
            return False, "Docker daemon is not running"
        return False, f"Sandbox image {self.image} is not built"

    async def execute(
        self,
        *,
        session_id: str,
        turn_id: str,
        command: str,
        cwd: str,
        timeout_seconds: float,
        network: bool,
        on_output: Callable[[dict], Awaitable[None]] | None = None,
        readonly_mounts: list[tuple[Path, str]] | None = None,
    ) -> SandboxResult:
        await self.recover_orphans()
        workspace = self.workspaces.session_root(session_id)
        working_directory = self.workspaces.resolve(session_id, cwd, must_exist=True)
        if not working_directory.is_dir():
            raise ToolError("invalid_working_directory", "Sandbox cwd must be a directory")
        relative_cwd = working_directory.relative_to(workspace).as_posix()
        container_name = f"symphony-{session_id[:8]}-{turn_id[:8]}-{uuid.uuid4().hex[:8]}"
        before = self._snapshot(workspace)
        container_cwd = "/workspace" if relative_cwd == "." else f"/workspace/{relative_cwd}"
        arguments = self.docker_arguments(
            workspace=workspace,
            container_name=container_name,
            container_cwd=container_cwd,
            command=command,
            network=network,
            readonly_mounts=readonly_mounts,
        )
        started = time.perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(
                self.docker_binary,
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
        except (FileNotFoundError, OSError) as exc:
            raise ToolError(
                "sandbox_unavailable",
                "Docker is unavailable. Install/start Docker and build the Symphony runtime image.",
            ) from exc
        self._containers[turn_id] = container_name
        self._processes[turn_id] = process
        try:
            stdout_task = asyncio.create_task(self._read_limited(process.stdout, "stdout", on_output))
            stderr_task = asyncio.create_task(self._read_limited(process.stderr, "stderr", on_output))
            try:
                stdout_result, stderr_result, exit_code = await asyncio.wait_for(
                    asyncio.gather(stdout_task, stderr_task, process.wait()),
                    timeout=timeout_seconds,
                )
            except TimeoutError as exc:
                await self._force_remove(container_name, process)
                raise ToolError(
                    "sandbox_timeout",
                    f"Sandbox command exceeded {timeout_seconds:g} seconds",
                    details={"command": command, "timeout_seconds": timeout_seconds},
                ) from exc
        except asyncio.CancelledError:
            await self._force_remove(container_name, process)
            raise
        finally:
            self._containers.pop(turn_id, None)
            self._processes.pop(turn_id, None)
        duration_ms = round((time.perf_counter() - started) * 1000)
        after = self._snapshot(workspace)
        changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
        stdout, stdout_truncated = stdout_result
        stderr, stderr_truncated = stderr_result
        if exit_code != 0:
            lowered = stderr.lower()
            code = "sandbox_command_failed"
            message = f"Sandbox command exited with code {exit_code}"
            if "cannot connect to the docker daemon" in lowered or "pipe" in lowered:
                code = "sandbox_unavailable"
                message = "Docker daemon is not running"
            elif "unable to find image" in lowered or "no such image" in lowered:
                code = "sandbox_image_missing"
                message = f"Sandbox image {self.image} is not built"
            raise ToolError(
                code,
                message,
                details={
                    "command": command,
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                    "changed_files": changed,
                    "output_truncated": stdout_truncated or stderr_truncated,
                    "duration_ms": duration_ms,
                },
            )
        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            changed_files=changed,
            output_truncated=stdout_truncated or stderr_truncated,
        )

    def docker_arguments(
        self,
        *,
        workspace: Path,
        container_name: str,
        container_cwd: str,
        command: str,
        network: bool,
        readonly_mounts: list[tuple[Path, str]] | None = None,
    ) -> list[str]:
        """Build a reviewable/testable containment contract for one execution."""
        arguments = [
            "run",
            "--rm",
            "--pull", "never",
            "--init",
            "--user", "10001:10001",
            "--label", f"com.symphony.instance={self.instance_id}",
            "--name",
            container_name,
            "--network",
            "bridge" if network else "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--pids-limit",
            str(self.pids_limit),
            "--memory",
            self.memory,
            "--cpus",
            str(self.cpus),
            "--security-opt",
            "no-new-privileges",
            "--cap-drop",
            "ALL",
            "--mount",
            f"type=bind,source={workspace},target=/workspace",
            "--workdir",
            container_cwd,
            "--env",
            "HOME=/tmp",
            "--env",
            "npm_config_cache=/tmp/.npm",
            "--env",
            "PIP_CACHE_DIR=/tmp/pip-cache",
        ]
        for source, target in readonly_mounts or []:
            source = source.resolve()
            if not source.is_dir() or is_link(source) or not target.startswith("/skill"):
                raise ToolError("invalid_mount", "Skill runtime mount is invalid")
            arguments.extend(["--mount", f"type=bind,source={source},target={target},readonly"])
        return [*arguments, self.image,
            "/bin/sh",
            "-lc",
            command,
        ]

    async def cancel(self, turn_id: str) -> None:
        container = self._containers.get(turn_id)
        process = self._processes.get(turn_id)
        if container and process:
            await self._force_remove(container, process)

    async def _read_limited(
        self,
        stream: asyncio.StreamReader | None,
        channel: str = "stdout",
        on_output: Callable[[dict], Awaitable[None]] | None = None,
    ) -> tuple[str, bool]:
        if stream is None:
            return "", False
        chunks: list[bytes] = []
        kept = 0
        truncated = False
        while chunk := await stream.read(8192):
            remaining = self.output_limit - kept
            if remaining > 0:
                piece = chunk[:remaining]
                chunks.append(piece)
                kept += len(piece)
                if on_output:
                    await on_output({"stream": channel, "delta": piece.decode("utf-8", errors="replace")})
            if len(chunk) > max(remaining, 0):
                truncated = True
        return b"".join(chunks).decode("utf-8", errors="replace"), truncated

    async def _force_remove(
        self,
        container_name: str,
        process: asyncio.subprocess.Process,
    ) -> None:
        try:
            cleanup = await asyncio.create_subprocess_exec(
                self.docker_binary,
                "rm",
                "--force",
                container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(cleanup.wait(), timeout=5)
        except (FileNotFoundError, OSError, TimeoutError):
            pass
        if process.returncode is None:
            process.kill()
            await process.wait()
        # docker run can be cancelled while Docker is still creating the container.
        # A second removal after its client exits closes that creation/removal race.
        try:
            await self._docker_control("rm", "--force", container_name)
        except (OSError, TimeoutError):
            self._recovery_done = False

    @staticmethod
    def _snapshot(root: Path) -> dict[str, tuple[int, str]]:
        snapshot: dict[str, tuple[int, str]] = {}
        for index, path in enumerate(walk_files(root, excluded={"node_modules", ".venv", ".git", "__pycache__"})):
            if index >= 5_000:
                break
            relative = path.relative_to(root).as_posix()
            size = path.stat().st_size
            if size <= 5_000_000:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                digest = f"mtime:{path.stat().st_mtime_ns}"
            snapshot[relative] = (size, digest)
        return snapshot
