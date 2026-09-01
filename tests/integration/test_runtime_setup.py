import hashlib
import io
import json
import os
import shutil
import subprocess
import zipfile

import pytest
from fastapi import HTTPException

from backend.api import setup


async def test_kit_is_fixed_self_contained_and_contains_no_user_data(client, monkeypatch):
    marker = "PRIVATE_CHAT_AND_ENV_98179"
    monkeypatch.setenv("OPENAI_API_KEY", marker)
    await client.post("/api/sessions", json={"title": marker})
    response = await client.get("/api/setup/runtime-kit?path=../../.env")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"symphony-runtime/" + name for name in (*setup.KIT_FILES, "SHA256SUMS", "manifest.json")}
        manifest = json.loads(archive.read("symphony-runtime/manifest.json"))
        assert manifest["image"] == "symphony-sandbox:stage3"
        assert manifest["runtime_version"] == "6.0"
        for name in setup.KIT_FILES:
            content = archive.read("symphony-runtime/" + name)
            assert marker.encode() not in content
            assert content == (setup.KIT_ROOT / name).read_bytes()
            assert hashlib.sha256(content).hexdigest() == manifest["sha256"][name]
        assert archive.getinfo("symphony-runtime/INSTALL.sh").external_attr >> 16 & 0o111
    assert (await client.post("/api/setup/runtime-kit")).status_code == 405


async def test_incomplete_packaging_returns_actionable_error_without_paths(client, monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "KIT_ROOT", tmp_path / "PRIVATE_PACKAGE_PATH")
    response = await client.get("/api/setup/runtime-kit")
    assert response.status_code == 503
    assert "Reinstall Symphony" in response.text
    assert "PRIVATE_PACKAGE_PATH" not in response.text


def test_kit_rejects_oversized_resources(tmp_path):
    (tmp_path / "Dockerfile").write_bytes(b"x" * 256_001)
    with pytest.raises(HTTPException) as error:
        setup.runtime_kit(tmp_path)
    assert error.value.status_code == 503


@pytest.mark.parametrize("answer,tamper,build_fails", [("n", False, False), ("y", False, False), ("y", True, False), ("y", False, True)])
def test_windows_installer_from_extracted_kit(tmp_path, answer, tamper, build_fails):
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not powershell:
        pytest.skip("PowerShell installer is verified on Windows")
    with zipfile.ZipFile(io.BytesIO(setup.runtime_kit(setup.KIT_ROOT))) as archive:
        archive.extractall(tmp_path)
    kit = tmp_path / "symphony-runtime"
    if tamper:
        (kit / "README.txt").write_text("modified")
    # Mock external Docker and confirmation only. Hashing, manifest validation,
    # script execution and exit behavior are real; no build/download occurs.
    harness = tmp_path / "harness.ps1"
    harness.write_text("""
function docker {
  $global:LASTEXITCODE = 0
  if ($args[0] -eq 'build') {
    Write-Output 'MOCK_BUILD_CALLED'
    $global:LASTEXITCODE = BUILD_CODE
  }
  if ($args[0] -eq 'image') { Write-Output '[{"Config":{"Labels":{"com.symphony.runtime.version":"6.0"}}}]' }
}
function Read-Host { return 'ANSWER' }
& (Join-Path $PSScriptRoot 'symphony-runtime/INSTALL.ps1')
""".replace("ANSWER", answer).replace("BUILD_CODE", "1" if build_fails else "0"), encoding="utf-8")
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness)], capture_output=True, timeout=30)
    output = result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace")
    assert ("MOCK_BUILD_CALLED" in output) is (answer == "y" and not tamper)
    assert (result.returncode != 0) is (tamper or build_fails)
    if answer == "n": assert "Nothing changed" in output
    if answer == "y" and not tamper and not build_fails: assert "Runtime ready" in output


@pytest.mark.parametrize("answer,tamper,build_fails", [("n", False, False), ("y", False, False), ("y", True, False), ("y", False, True)])
def test_bash_installer_from_extracted_kit(tmp_path, answer, tamper, build_fails):
    if os.getenv("SYMPHONY_RUN_DOCKER_TESTS") != "1":
        pytest.skip("Set SYMPHONY_RUN_DOCKER_TESTS=1 to exercise the Bash installer in the existing runtime")
    with zipfile.ZipFile(io.BytesIO(setup.runtime_kit(setup.KIT_ROOT))) as archive:
        archive.extractall(tmp_path)
    if tamper:
        (tmp_path / "symphony-runtime" / "README.txt").write_text("modified")
    # Real Bash + shasum, simulated external Docker; no engine socket/network.
    (tmp_path / "mock-docker").write_text('''#!/usr/bin/env bash
case "$1" in
  build) echo MOCK_BUILD_CALLED; exit BUILD_CODE;;
  image) echo 6.0;;
  info) exit 0;;
  *) exit 2;;
esac
'''.replace("BUILD_CODE", "1" if build_fails else "0"), encoding="utf-8", newline="\n")
    command = 'docker() { bash /kit/mock-docker "$@"; }; export -f docker; printf "%s\\n" ' + answer + ' | bash /kit/symphony-runtime/INSTALL.sh'
    result = subprocess.run(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "128m", "--cpus", "1", "--pids-limit", "64", "--mount", f"type=bind,source={tmp_path},target=/kit,readonly", "symphony-sandbox:stage3", "bash", "-c", command], capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    assert ("MOCK_BUILD_CALLED" in output) is (answer == "y" and not tamper), output
    assert (result.returncode != 0) is (tamper or build_fails), output
    if answer == "n": assert "Nothing changed" in output
    if answer == "y" and not tamper and not build_fails: assert "Runtime ready" in output
