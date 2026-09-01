from pathlib import Path

from backend.sandbox.policy import PolicyEngine
from backend.tools.sandbox import ShellTool
from backend.tools.workspace import WorkspaceManager


class RuntimeStub:
    async def execute(self, **kwargs):  # pragma: no cover - policy test never executes
        raise AssertionError("not called")


def shell_tool(tmp_path: Path) -> ShellTool:
    RuntimeStub.workspaces = WorkspaceManager(tmp_path / "workspaces")
    return ShellTool(RuntimeStub())  # type: ignore[arg-type]


def test_restricted_profile_requires_approval_for_network_or_install(tmp_path):
    decision = PolicyEngine().evaluate(
        shell_tool(tmp_path),
        {"command": "npm install", "network": True},
        profile="build",
    )
    assert decision.action == "approval_required"
    assert decision.risk_level == "medium"


def test_all_profiles_require_approval_for_install(tmp_path):
    tool = shell_tool(tmp_path)
    engine = PolicyEngine()
    for profile in ("read_only", "project_edit", "build", "full_manual"):
        assert engine.evaluate(tool, {"command": "pip install fastapi"}, profile=profile).action == "approval_required"


def test_hard_denies_apply_to_every_profile(tmp_path):
    decision = PolicyEngine().evaluate(
        shell_tool(tmp_path),
        {"command": "mount /dev/sda /mnt"},
        profile="full_manual",
    )
    assert decision.action == "deny"
    assert decision.risk_level == "high"


def test_safe_workspace_command_is_allowed_without_prompt(tmp_path):
    decision = PolicyEngine().evaluate(
        shell_tool(tmp_path),
        {"command": "npm run build && npm test", "network": False},
        profile="build",
    )
    assert decision.action == "allow"
