from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _bash() -> str:
    git_bash = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
    if git_bash.exists():
        return str(git_bash)
    command = shutil.which("bash")
    assert command, "bash is required to exercise the macOS launcher"
    return command


def _executable(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -e\n" + body, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _shell_path(path: Path) -> str:
    resolved_path = path.resolve()
    windows_temp = Path(tempfile.gettempdir()).resolve()
    try:
        return "/tmp/" + resolved_path.relative_to(windows_temp).as_posix()
    except ValueError:
        pass
    resolved = resolved_path.as_posix()
    if len(resolved) >= 3 and resolved[1:3] == ":/":
        return f"/{resolved[0].lower()}/{resolved[3:]}"
    return resolved


class MacOSLauncherTests(unittest.TestCase):
    def test_starts_backend_and_opens_browser_when_dependencies_are_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._assert_ready_launch(Path(temporary))

    def _assert_ready_launch(self, tmp_path: Path) -> None:
        root = tmp_path / "Symphony"
        scripts = root / "scripts"
        fake_bin = tmp_path / "bin"
        scripts.mkdir(parents=True)
        fake_bin.mkdir()
        (root / "frontend" / "dist").mkdir(parents=True)
        (root / "frontend" / "dist" / "index.html").write_text("ready", encoding="utf-8")
        (root / ".venv" / "bin").mkdir(parents=True)
        launcher = PROJECT_ROOT / "scripts" / "start-macos.sh"
        command_file = PROJECT_ROOT / "START.command"
        shutil.copy2(launcher, scripts / launcher.name)
        shutil.copy2(command_file, root / command_file.name)

        calls = tmp_path / "calls.log"
        ready = tmp_path / "backend-ready"
        _executable(fake_bin / "uname", 'echo Darwin\n')
        _executable(fake_bin / "docker", 'if [[ "$1 $2" == "image inspect" ]]; then echo 6.0; fi\n')
        _executable(fake_bin / "ollama", 'echo "ollama $*" >> "$CALLS"\n')
        _executable(fake_bin / "open", 'echo "open $*" >> "$CALLS"\n')
        _executable(
            fake_bin / "curl",
            '[[ "$*" == *"11434/api/tags"* ]] && exit 0\n'
            '[[ "$*" == *"8765/api/health"* && -f "$READY" ]] && exit 0\n'
            'exit 22\n',
        )
        _executable(
            root / ".venv" / "bin" / "python",
            'echo "python $*" >> "$CALLS"\n'
            '[[ "$*" == *"uvicorn backend.main:app"* ]] && touch "$READY"\n'
            'exit 0\n',
        )

        environment = os.environ.copy()
        # The fake backend is immediate, but Git Bash process startup can take
        # several seconds on a loaded Windows CI host. Keep this well below the
        # launcher's 30-second production default without making the test flaky.
        environment.update(SYMPHONY_START_TIMEOUT="7")
        command = (
            f'export PATH="{_shell_path(fake_bin)}:/usr/bin:$PATH"; '
            f'export CALLS="{_shell_path(calls)}" READY="{_shell_path(ready)}"; '
            f'bash "{_shell_path(root / "START.command")}"'
        )
        result = subprocess.run(
            [_bash(), "-c", command],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FinCtrl", result.stdout)
        self.assertNotIn("Symphony", result.stdout)
        observed = calls.read_text(encoding="utf-8")
        self.assertIn("python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765", observed)
        self.assertIn("open http://127.0.0.1:8765", observed)
        self.assertIn("ollama show qwen3.5:9b", observed)


if __name__ == "__main__":
    unittest.main()
