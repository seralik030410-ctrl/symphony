from __future__ import annotations

import os
import re
import threading
from collections.abc import Mapping


SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|authorization|password|secret|token)", re.I)


class SecretStore:
    """Resolve opaque secret references without persisting secret values in SQLite."""

    def __init__(self, injected: Mapping[str, str] | None = None) -> None:
        self._values = {str(key): str(value) for key, value in (injected or {}).items() if value}
        self._lock = threading.RLock()

    def set_memory(self, reference_id: str, value: str) -> None:
        clean = value.strip()
        if not clean or len(clean) > 4096:
            raise ValueError("Secret must contain from 1 to 4096 characters")
        with self._lock:
            self._values[reference_id] = clean

    def remove_memory(self, reference_id: str) -> None:
        with self._lock:
            self._values.pop(reference_id, None)

    def has(self, reference_id: str) -> bool:
        with self._lock:
            return bool(self._values.get(reference_id))

    def resolve(self, reference_id: str, storage_kind: str, locator: str) -> str:
        if storage_kind == "environment":
            return os.getenv(locator, "")
        with self._lock:
            return self._values.get(reference_id, "")

    def redact_text(self, value: str) -> str:
        result = value
        with self._lock:
            secrets = tuple(secret for secret in self._values.values() if len(secret) >= 4)
        for secret in secrets:
            result = result.replace(secret, "***")
        return result

    def redact(self, value):
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.redact(item) for item in value)
        if isinstance(value, dict):
            return {
                key: "***" if SENSITIVE_KEY.search(str(key)) and item not in (None, "", False) else self.redact(item)
                for key, item in value.items()
            }
        return value
