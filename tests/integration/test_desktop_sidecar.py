"""Exercise the real Python sidecar pipe/lifecycle; no Rust or native UI claims."""
import asyncio
import io
import json
import os
from pathlib import Path
import socket
import sys

import httpx
import pytest

from desktop.sidecar import read_bootstrap

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("payload", [b"", b"{}\n", b"not-json\n", b'{"protocol":2,"openai_api_key":""}\n',
                                     b'{"protocol":1,"openai_api_key":42}\n',
                                     b'{"protocol":1,"openai_api_key":"secret","extra":true}\n', b"x" * 20_001])
def test_bootstrap_rejects_malformed_input_without_echo(payload):
    with pytest.raises(ValueError, match="^Invalid desktop bootstrap protocol$"):
        read_bootstrap(io.BytesIO(payload))


def test_bootstrap_accepts_only_bounded_secret():
    assert read_bootstrap(io.BytesIO(b'{"protocol":1,"openai_api_key":"private"}\n'))["openai_api_key"] == "private"


async def start_sidecar(tmp_path, port=0):
    env = {**os.environ, "SYMPHONY_PORT": str(port), "SYMPHONY_DATABASE_PATH": str(tmp_path / "desktop.db"),
           "SYMPHONY_WORKSPACE_ROOT": str(tmp_path / "workspaces"), "SYMPHONY_SKILLS_ROOT": str(tmp_path / "skills"),
           "SYMPHONY_SEED_BUNDLED_SKILLS": "0", "SYMPHONY_OPENAI_API_KEY": "INHERITED_KEY_MUST_NOT_LEAK"}
    # CI can rerun these lifecycle checks against the actual PyInstaller binary.
    command = [env["SYMPHONY_TEST_SIDECAR"]] if env.get("SYMPHONY_TEST_SIDECAR") else [sys.executable, "-m", "desktop.sidecar"]
    process = await asyncio.create_subprocess_exec(*command, cwd=ROOT, env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    process.stdin.write(b'{"protocol":1,"openai_api_key":"PIPE_KEY_MUST_NOT_LEAK"}\n')
    await process.stdin.drain()
    return process


async def cleanup(process):
    if process.returncode is None:
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 15)
        except TimeoutError:
            process.kill()
            await process.wait()


@pytest.mark.parametrize("shutdown", ["eof", "command"])
async def test_ready_only_after_migration_and_stop_with_parent(tmp_path, shutdown):
    process = await start_sidecar(tmp_path)
    try:
        line = await asyncio.wait_for(process.stdout.readline(), 30)
        assert line, (await process.stderr.read()).decode(errors="replace")
        ready = json.loads(line)
        assert ready["event"] == "symphony.ready" and ready["protocol"] == 1
        assert (tmp_path / "desktop.db").is_file()
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(f"http://127.0.0.1:{ready['port']}/api/sessions")
            assert response.status_code == 200 and response.json() == []
        if shutdown == "command":
            process.stdin.write(b'{"command":"shutdown"}\n')
            await process.stdin.drain()
        else:
            process.stdin.close()
        await asyncio.wait_for(process.wait(), 15)
        assert process.returncode == 0
        output = line + await process.stdout.read() + await process.stderr.read()
        assert b"PIPE_KEY_MUST_NOT_LEAK" not in output and b"INHERITED_KEY_MUST_NOT_LEAK" not in output
        assert output.count(b"symphony.ready") == 1
    finally:
        await cleanup(process)


async def test_occupied_port_cannot_open_database_or_emit_ready(tmp_path):
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        process = await start_sidecar(tmp_path, occupied.getsockname()[1])
        try:
            await asyncio.wait_for(process.wait(), 20)
            assert process.returncode != 0
            assert not (tmp_path / "desktop.db").exists()
            assert b"symphony.ready" not in await process.stdout.read()
            errors = await process.stderr.read()
            assert b"PIPE_KEY_MUST_NOT_LEAK" not in errors
        finally:
            await cleanup(process)
