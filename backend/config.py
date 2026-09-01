from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    database_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "symphony.db")
    workspace_root: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "workspaces")
    skills_root: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "skills")
    bundled_skills_root: Path = field(default_factory=lambda: PROJECT_ROOT / "bundled-skills")
    seed_bundled_skills: bool = True
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b"
    openai_base_url: str = "http://127.0.0.1:1234/v1"
    openai_model: str = "local-model"
    openai_api_key: str = ""
    openai_profile_name: str = "OpenAI-compatible API"
    provider_timeout_seconds: float = 120.0
    discovery_timeout_seconds: float = 2.0
    default_context_window: int = 16_384
    default_max_output: int = 2_048
    max_tool_calls: int = 12
    tool_timeout_seconds: float = 10.0
    sandbox_image: str = "symphony-sandbox:stage3"
    sandbox_memory: str = "768m"
    sandbox_cpus: float = 1.5
    sandbox_pids_limit: int = 256
    sandbox_output_limit: int = 100_000

    @classmethod
    def from_env(cls) -> "Settings":
        raw_db = Path(os.getenv("SYMPHONY_DATABASE_PATH", "data/symphony.db"))
        database_path = raw_db if raw_db.is_absolute() else PROJECT_ROOT / raw_db
        raw_workspaces = Path(os.getenv("SYMPHONY_WORKSPACE_ROOT", "data/workspaces"))
        workspace_root = raw_workspaces if raw_workspaces.is_absolute() else PROJECT_ROOT / raw_workspaces
        raw_skills = Path(os.getenv("SYMPHONY_SKILLS_ROOT", "data/skills"))
        skills_root = raw_skills if raw_skills.is_absolute() else PROJECT_ROOT / raw_skills
        return cls(
            host=os.getenv("SYMPHONY_HOST", "127.0.0.1"),
            port=int(os.getenv("SYMPHONY_PORT", "8765")),
            database_path=database_path,
            workspace_root=workspace_root,
            skills_root=skills_root,
            bundled_skills_root=PROJECT_ROOT / "bundled-skills",
            seed_bundled_skills=os.getenv("SYMPHONY_SEED_BUNDLED_SKILLS", "1") != "0",
            cors_origins=_csv(
                os.getenv(
                    "SYMPHONY_CORS_ORIGINS",
                    "http://localhost:5173,http://127.0.0.1:5173",
                )
            ),
            ollama_base_url=os.getenv("SYMPHONY_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=os.getenv("SYMPHONY_OLLAMA_MODEL", "qwen3.5:9b"),
            openai_base_url=os.getenv("SYMPHONY_OPENAI_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/"),
            openai_model=os.getenv("SYMPHONY_OPENAI_MODEL", "local-model"),
            openai_api_key=os.getenv("SYMPHONY_OPENAI_API_KEY", ""),
            openai_profile_name=os.getenv(
                "SYMPHONY_OPENAI_PROFILE_NAME", "OpenAI-compatible API"
            ).strip() or "OpenAI-compatible API",
            provider_timeout_seconds=float(os.getenv("SYMPHONY_PROVIDER_TIMEOUT_SECONDS", "120")),
            discovery_timeout_seconds=float(os.getenv("SYMPHONY_DISCOVERY_TIMEOUT_SECONDS", "2")),
            default_context_window=int(os.getenv("SYMPHONY_DEFAULT_CONTEXT_WINDOW", "16384")),
            default_max_output=int(os.getenv("SYMPHONY_DEFAULT_MAX_OUTPUT", "2048")),
            max_tool_calls=int(os.getenv("SYMPHONY_MAX_TOOL_CALLS", "12")),
            tool_timeout_seconds=float(os.getenv("SYMPHONY_TOOL_TIMEOUT_SECONDS", "10")),
            sandbox_image=os.getenv("SYMPHONY_SANDBOX_IMAGE", "symphony-sandbox:stage3"),
            sandbox_memory=os.getenv("SYMPHONY_SANDBOX_MEMORY", "768m"),
            sandbox_cpus=float(os.getenv("SYMPHONY_SANDBOX_CPUS", "1.5")),
            sandbox_pids_limit=int(os.getenv("SYMPHONY_SANDBOX_PIDS_LIMIT", "256")),
            sandbox_output_limit=int(os.getenv("SYMPHONY_SANDBOX_OUTPUT_LIMIT", "100000")),
        )
