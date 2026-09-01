from backend.sandbox.runtime import DockerSandboxRuntime
from backend.tools.workspace import WorkspaceManager


def test_docker_arguments_enforce_containment_and_no_network_by_default(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces")
    workspace = manager.session_root("a" * 32)
    runtime = DockerSandboxRuntime(manager, image="symphony-test:stage3")
    arguments = runtime.docker_arguments(
        workspace=workspace,
        container_name="symphony-test",
        container_cwd="/workspace",
        command="npm test",
        network=False,
    )

    assert arguments[arguments.index("--network") + 1] == "none"
    assert "--read-only" in arguments
    assert [arguments[index + 1] for index, value in enumerate(arguments) if value == "--cap-drop"] == ["ALL"]
    assert [arguments[index + 1] for index, value in enumerate(arguments) if value == "--security-opt"] == ["no-new-privileges"]
    mounts = [arguments[index + 1] for index, value in enumerate(arguments) if value == "--mount"]
    assert mounts == [f"type=bind,source={workspace},target=/workspace"]
    assert "HOME=/tmp" in arguments
    assert arguments[-3:] == ["/bin/sh", "-lc", "npm test"]


def test_network_is_enabled_only_when_policy_passes_true(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces")
    runtime = DockerSandboxRuntime(manager, image="symphony-test:stage3")
    arguments = runtime.docker_arguments(
        workspace=manager.session_root("b" * 32),
        container_name="symphony-test",
        container_cwd="/workspace/app",
        command="npm install",
        network=True,
    )
    assert arguments[arguments.index("--network") + 1] == "bridge"
    assert arguments[arguments.index("--workdir") + 1] == "/workspace/app"
