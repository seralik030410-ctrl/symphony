from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from backend.tools.contracts import Tool


PolicyAction = Literal["allow", "approval_required", "deny"]


@dataclass(slots=True)
class PolicyDecision:
    action: PolicyAction
    reason: str
    risk_level: Literal["low", "medium", "high"] = "low"


class PolicyEngine:
    """Classifies requested capabilities; Docker containment remains a separate layer."""

    HARD_DENY = (
        re.compile(r"(?:^|\s)(?:mkfs|mount|umount|shutdown|reboot)(?:\s|$)", re.I),
        re.compile(r":\(\)\s*\{\s*:\|:&\s*;\s*\}\s*;\s*:", re.I),
        re.compile(r"/dev/(?:sd|nvme|mem|kmem)", re.I),
        re.compile(r"docker\.sock|/var/run/docker", re.I),
    )
    DESTRUCTIVE = (
        re.compile(r"(?:^|[;&|]\s*)rm\s+-[^\n]*r", re.I),
        re.compile(r"(?:^|[;&|]\s*)git\s+(?:reset\s+--hard|clean\s+-|push\s+.*--force)", re.I),
        re.compile(r"(?:^|[;&|]\s*)(?:del|rmdir)\b", re.I),
    )
    INSTALL_OR_NETWORK = (
        re.compile(r"(?:^|[;&|]\s*)(?:npm|pnpm|yarn)\s+(?:install|add|i)\b", re.I),
        re.compile(r"(?:^|[;&|]\s*)(?:pip|pip3|python\s+-m\s+pip)\s+install\b", re.I),
        re.compile(r"(?:^|[;&|]\s*)(?:apt|apt-get|apk|dnf|yum)\b", re.I),
        re.compile(r"(?:^|[;&|]\s*)(?:curl|wget|ssh|scp|nc|ncat)\b", re.I),
    )

    def evaluate(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        *,
        profile: str,
        session_id: str | None = None,
    ) -> PolicyDecision:
        if profile not in {"read_only", "project_edit", "build", "full_manual"}:
            return PolicyDecision("deny", "Unknown permission profile", "high")
        if tool.open_world and hasattr(tool, "network_policy"):
            if session_id is None:
                return PolicyDecision("deny", "Network tools need an explicit session")
            return tool.network_policy(session_id, arguments)
        if tool.open_world and tool.read_only:
            return PolicyDecision("deny", "Unregistered network policy")
        if tool.read_only:
            return PolicyDecision("allow", "Read-only workspace operation")
        if tool.name == "skill.run_script":
            return PolicyDecision("approval_required", "Review this skill script and its arguments before isolated execution", "medium")
        if tool.name != "sandbox.shell":
            if tool.destructive or profile in {"read_only", "full_manual"}:
                return PolicyDecision("approval_required", "This profile requires approval before writing files", "medium")
            return PolicyDecision("allow", "Workspace edit with a recoverable snapshot")
        command = str(arguments.get("command", ""))
        for pattern in self.HARD_DENY:
            if pattern.search(command):
                return PolicyDecision(
                    "deny",
                    "The command requests a capability that the sandbox never exposes",
                    "high",
                )
        destructive = any(pattern.search(command) for pattern in self.DESTRUCTIVE)
        install_or_network = bool(arguments.get("network")) or any(
            pattern.search(command) for pattern in self.INSTALL_OR_NETWORK
        )
        if destructive:
            return PolicyDecision(
                "approval_required",
                "This command can delete or rewrite workspace history",
                "high",
            )
        if install_or_network:
            return PolicyDecision(
                "approval_required",
                "This command requests package installation or network access",
                "medium",
            )
        # This is a permission classification, not a shell security parser. Arbitrary
        # script contents still run only in the container, with a pre-command snapshot.
        # Metacharacters, redirects, substitutions and unknown commands always prompt.
        build_pattern = (
            r"(?:npm (?:test|run (?:build|test|lint|typecheck))|"
            r"(?:python(?:3)? -m )?pytest(?: [a-zA-Z0-9_./=-]+)*|"
            r"node --test(?: [a-zA-Z0-9_./-]+)*)"
        )
        # A chain of known builds is still a local build. No other shell grammar
        # is accepted (including empty segments, |, ;, substitutions or redirects).
        local_build = all(re.fullmatch(build_pattern, part.strip()) for part in command.split("&&"))
        if profile == "build" and local_build:
            return PolicyDecision("allow", "Offline project test/build with a recoverable snapshot")
        return PolicyDecision("approval_required", "Review this shell command before it changes the project", "medium")
