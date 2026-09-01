from __future__ import annotations

from dataclasses import dataclass

from backend.storage.repository import Repository
from backend.models.base import ProviderError
from backend.models.tokens import estimate_tokens


@dataclass(slots=True)
class ContextPack:
    messages: list[dict[str, str]]
    estimated_tokens: int
    context_window: int
    dropped_messages: int


class ContextBuilder:
    """Builds bounded context from exactly one session."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def build(self, session_id: str, *, system_suffix: str = "", reserved_tokens: int = 0,
              memory_source_ids: set[str] | None = None, evidence: str = "") -> ContextPack:
        session = self.repository.get_session(session_id, include_history=False)
        excluded = memory_source_ids or set()
        records = [item for item in self.repository.list_context_records(session_id) if item["id"] not in excluded]
        history = [{"role": item["role"], "content": item["content"]} for item in records]
        system = {"role": "system", "content": session["system_prompt"] + ("\n\n" + system_suffix if system_suffix else "")}
        evidence_messages = [{"role": "user", "content": evidence}] if evidence else []
        budget = max(1, session["context_window"] - session["max_output"] - reserved_tokens)
        selected: list[dict[str, str]] = []
        used = self.estimate_tokens([system, *evidence_messages])
        for message in reversed(history):
            cost = self.estimate_tokens([message])
            if used + cost > budget:
                raise ProviderError("Контекст не помещается без потери сообщений. Увеличьте окно, сократите вложения или сожмите память в настройках. История сохранена.", code="context_limit")
            selected.append(message)
            used += cost
        selected.reverse()
        messages = [system, *evidence_messages, *selected]
        return ContextPack(
            messages=messages,
            estimated_tokens=self.estimate_tokens(messages),
            context_window=session["context_window"],
            dropped_messages=max(0, len(history) - len(selected)),
        )

    @staticmethod
    def estimate_tokens(messages: list[dict[str, str]]) -> int:
        return estimate_tokens(messages)
