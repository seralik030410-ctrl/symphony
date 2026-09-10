from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any

from backend.config import Settings
from backend.models.base import Capability, ModelAdapter, ModelCapabilities, ProviderError
from backend.models.ollama import OllamaAdapter
from backend.models.openai_compatible import OpenAICompatibleAdapter
from backend.providers.secrets import SecretStore
from backend.storage.database import Database, utc_now
from backend.storage.repository import ConflictError, NotFoundError


BUILTIN_OLLAMA = "builtin-ollama"
BUILTIN_OPENAI = "builtin-openai"


class ProviderRegistry:
    """Durable provider metadata and capability selection; streaming remains in ModelGateway."""

    def __init__(self, database: Database, settings: Settings, secrets: SecretStore) -> None:
        self.database = database
        self.settings = settings
        self.secrets = secrets
        self._adapters: dict[str, ModelAdapter] = {}
        self.ensure_defaults()

    def ensure_defaults(self) -> None:
        now = utc_now()
        rows = (
            (BUILTIN_OLLAMA, "ollama", "Ollama", self.settings.ollama_base_url, self.settings.ollama_model, 1, 1, None),
            (BUILTIN_OPENAI, "openai_compatible", self.settings.openai_profile_name, self.settings.openai_base_url, self.settings.openai_model, 1, 0, "builtin-openai-secret"),
        )
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO provider_secret_refs(id,storage_kind,locator,created_at,updated_at) VALUES(?,?,?,?,?)",
                ("builtin-openai-secret", "memory", "openai-compatible-api-key", now, now),
            )
            for profile_id, kind, title, url, model, enabled, local, secret_ref in rows:
                connection.execute(
                    """INSERT OR IGNORE INTO provider_profiles(
                       id,provider_type,title,base_url,default_model,enabled,is_local,secret_ref_id,
                       request_timeout_seconds,discovery_timeout_seconds,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (profile_id, kind, title, url, model, enabled, local, secret_ref,
                     self.settings.provider_timeout_seconds, self.settings.discovery_timeout_seconds, now, now),
                )
        if self.settings.openai_api_key and not self.secrets.has("builtin-openai-secret"):
            self.secrets.set_memory("builtin-openai-secret", self.settings.openai_api_key)

    @staticmethod
    def _base_capabilities(profile: dict[str, Any], model: str) -> ModelCapabilities:
        if profile["provider_type"] == "ollama":
            return ModelCapabilities(text=True, native_tools=True, reasoning_stream=True)
        return ModelCapabilities(text=True, native_tools=True, max_context=131_072, max_output=4_096)

    def _secret(self, profile: dict[str, Any]) -> str:
        reference_id = profile.get("secret_ref_id") or profile.get("secret", {}).get("reference_id")
        if not reference_id:
            return ""
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT storage_kind,locator FROM provider_secret_refs WHERE id=?", (reference_id,)
            ).fetchone()
        return self.secrets.resolve(reference_id, row["storage_kind"], row["locator"]) if row else ""

    def adapter(self, profile_id: str) -> ModelAdapter:
        cached = self._adapters.get(profile_id)
        if cached is not None:
            return cached
        profile = self.get(profile_id, include_health=True)
        if not profile["enabled"]:
            raise ProviderError("Provider profile is disabled", code="provider_disabled")
        common = dict(
            request_timeout=profile["request_timeout_seconds"],
            discovery_timeout=profile["discovery_timeout_seconds"],
        )
        if profile["provider_type"] == "ollama":
            adapter: ModelAdapter = OllamaAdapter(profile["base_url"], profile["default_model"], **common)
        else:
            adapter = OpenAICompatibleAdapter(
                profile["base_url"], profile["default_model"], self._secret(profile),
                profile_title=profile["title"], **common,
            )
        self._adapters[profile_id] = adapter
        return adapter

    def _row(self, row: Any) -> dict[str, Any]:
        value = dict(row)
        value["enabled"] = bool(value["enabled"])
        value["is_local"] = bool(value["is_local"])
        value["last_health_ok"] = None if value["last_health_ok"] is None else bool(value["last_health_ok"])
        value["config"] = json.loads(value.pop("config_json"))
        reference_id = value.pop("secret_ref_id")
        value["secret"] = {
            "configured": bool(reference_id and self._secret({**value, "secret_ref_id": reference_id})),
            "reference_id": reference_id,
            "masked": "••••••••" if reference_id and self._secret({**value, "secret_ref_id": reference_id}) else None,
        }
        return value

    def list(self) -> list[dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT * FROM provider_profiles ORDER BY title COLLATE NOCASE,id").fetchall()
        return [self._row(row) for row in rows]

    def get(self, profile_id: str, *, include_health: bool = False) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM provider_profiles WHERE id=?", (profile_id,)).fetchone()
        if not row:
            raise NotFoundError("Provider profile not found")
        value = self._row(row)
        if not include_health:
            value.pop("last_health_message", None)
        return value

    def create(self, values: dict[str, Any], *, secret: str | None = None) -> dict[str, Any]:
        for capability in values.get("capabilities", {}):
            Capability(capability)
        profile_id = uuid.uuid4().hex
        secret_env_var = values.get("secret_env_var")
        secret_ref_id = uuid.uuid4().hex if secret or secret_env_var else None
        now = utc_now()
        with self.database.transaction() as connection:
            if secret_ref_id:
                connection.execute(
                    "INSERT INTO provider_secret_refs(id,storage_kind,locator,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (secret_ref_id,
                     "environment" if secret_env_var else "desktop" if values.get("secret_storage") == "desktop" else "memory",
                     secret_env_var or f"provider:{profile_id}", now, now),
                )
            connection.execute(
                """INSERT INTO provider_profiles(id,provider_type,title,base_url,default_model,enabled,is_local,
                   secret_ref_id,request_timeout_seconds,discovery_timeout_seconds,config_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (profile_id, values["provider_type"], values["title"].strip(), values["base_url"].rstrip("/"),
                 values["default_model"].strip(), int(values.get("enabled", True)), int(values.get("is_local", False)),
                 secret_ref_id, values.get("request_timeout_seconds", 120), values.get("discovery_timeout_seconds", 2),
                 json.dumps(values.get("config", {}), ensure_ascii=False), now, now),
            )
        if secret_ref_id and secret:
            self.secrets.set_memory(secret_ref_id, secret)
        for capability, enabled in values.get("capabilities", {}).items():
            self.set_capability(profile_id, values["default_model"], capability, enabled)
        return self.get(profile_id, include_health=True)

    def update(self, profile_id: str, values: dict[str, Any], *, secret: str | None = None, clear_secret: bool = False) -> dict[str, Any]:
        for capability in values.get("capabilities", {}):
            Capability(capability)
        current = self.get(profile_id, include_health=True)
        allowed = {"title", "base_url", "default_model", "enabled", "is_local", "request_timeout_seconds", "discovery_timeout_seconds", "config"}
        updates = {key: value for key, value in values.items() if key in allowed and value is not None}
        if "base_url" in updates:
            updates["base_url"] = updates["base_url"].rstrip("/")
        if "config" in updates:
            updates["config_json"] = json.dumps(updates.pop("config"), ensure_ascii=False)
        for key in ("enabled", "is_local"):
            if key in updates:
                updates[key] = int(updates[key])
        reference_id = current["secret"]["reference_id"]
        now = utc_now()
        with self.database.transaction() as connection:
            secret_env_var = values.get("secret_env_var")
            if (secret or secret_env_var) and not reference_id:
                reference_id = uuid.uuid4().hex
                connection.execute(
                    "INSERT INTO provider_secret_refs(id,storage_kind,locator,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (reference_id,
                     "environment" if secret_env_var else "desktop" if values.get("secret_storage") == "desktop" else "memory",
                     secret_env_var or f"provider:{profile_id}", now, now),
                )
                updates["secret_ref_id"] = reference_id
            elif secret_env_var and reference_id:
                connection.execute(
                    "UPDATE provider_secret_refs SET storage_kind='environment',locator=?,updated_at=? WHERE id=?",
                    (secret_env_var, now, reference_id),
                )
            if clear_secret and reference_id:
                updates["secret_ref_id"] = None
            updates["updated_at"] = now
            assignments = ",".join(f"{key}=?" for key in updates)
            connection.execute(f"UPDATE provider_profiles SET {assignments} WHERE id=?", (*updates.values(), profile_id))
            if clear_secret and reference_id:
                connection.execute("DELETE FROM provider_secret_refs WHERE id=?", (reference_id,))
        if secret and reference_id:
            self.secrets.set_memory(reference_id, secret)
        if clear_secret and reference_id:
            self.secrets.remove_memory(reference_id)
        self._adapters.pop(profile_id, None)
        model = values.get("default_model", current["default_model"])
        for capability, enabled in values.get("capabilities", {}).items():
            self.set_capability(profile_id, model, capability, enabled)
        return self.get(profile_id, include_health=True)

    def delete(self, profile_id: str) -> None:
        if profile_id in {BUILTIN_OLLAMA, BUILTIN_OPENAI}:
            raise ConflictError("Built-in profiles can be disabled, but not deleted")
        current = self.get(profile_id, include_health=True)
        reference_id = current["secret"]["reference_id"]
        with self.database.transaction() as connection:
            used = connection.execute(
                "SELECT 1 FROM sessions WHERE provider_profile_id=? LIMIT 1", (profile_id,)
            ).fetchone()
            if used:
                raise ConflictError("Provider profile is used by an active chat")
            cursor = connection.execute("DELETE FROM provider_profiles WHERE id=?", (profile_id,))
            if reference_id:
                connection.execute("DELETE FROM provider_secret_refs WHERE id=?", (reference_id,))
        if not cursor.rowcount:
            raise NotFoundError("Provider profile not found")
        if reference_id:
            self.secrets.remove_memory(reference_id)
        self._adapters.pop(profile_id, None)

    def capability_overrides(self, profile_id: str, model: str) -> dict[str, bool]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT capability,enabled FROM provider_capability_overrides WHERE profile_id=? AND model=?",
                (profile_id, model),
            ).fetchall()
        return {row["capability"]: bool(row["enabled"]) for row in rows}

    def capabilities(self, profile_id: str, model: str, detected: ModelCapabilities | None = None) -> ModelCapabilities:
        profile = self.get(profile_id, include_health=True)
        capabilities = detected or self._base_capabilities(profile, model)
        for name, enabled in self.capability_overrides(profile_id, model).items():
            capabilities.set_support(name, enabled)
        return capabilities

    def set_capability(self, profile_id: str, model: str, capability: str, enabled: bool) -> None:
        self.get(profile_id)
        Capability(capability)
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO provider_capability_overrides(profile_id,model,capability,enabled,updated_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(profile_id,model,capability) DO UPDATE SET
                   enabled=excluded.enabled,updated_at=excluded.updated_at""",
                (profile_id, model, capability, int(enabled), utc_now()),
            )

    def select(self, capability: Capability | str, *, model: str | None = None) -> dict[str, Any]:
        required = Capability(capability)
        for profile in self.list():
            if not profile["enabled"] or (model and profile["default_model"] != model):
                continue
            if self.capabilities(profile["id"], model or profile["default_model"]).supports(required):
                return profile
        raise ProviderError(f"No enabled provider supports {required.value}", code="capability_unavailable")

    def speech_endpoint(self, profile_id: str, capability: Capability | str) -> dict[str, Any]:
        required = Capability(capability)
        if required not in {Capability.AUDIO_TRANSCRIPTION, Capability.AUDIO_SYNTHESIS}:
            raise ProviderError("Requested capability is not a modular speech capability", code="capability_unavailable")
        profile = self.get(profile_id, include_health=True)
        if not profile["enabled"]:
            raise ProviderError("Provider profile is disabled", code="provider_disabled")
        if not self.capabilities(profile_id, profile["default_model"]).supports(required):
            raise ProviderError(f"Provider profile does not support {required.value}", code="capability_unavailable")
        return {
            "profile_id": profile_id,
            "base_url": profile["base_url"].rstrip("/"),
            "model": profile["default_model"],
            "api_key": self._secret({**profile, "secret_ref_id": profile["secret"]["reference_id"]}),
            "timeout": profile["request_timeout_seconds"],
            "is_local": profile["is_local"],
        }

    def realtime_endpoint(self, profile_id: str) -> dict[str, Any]:
        profile = self.get(profile_id, include_health=True)
        if not profile["enabled"]:
            raise ProviderError("Provider profile is disabled", code="provider_disabled")
        if not self.capabilities(profile_id, profile["default_model"]).supports(Capability.AUDIO_REALTIME):
            raise ProviderError("Provider profile does not support audio.realtime", code="capability_unavailable")
        if profile["provider_type"] != "openai_compatible":
            raise ProviderError("This provider needs a dedicated realtime adapter", code="realtime_adapter_unavailable")
        return {
            "profile_id": profile_id,
            "base_url": profile["base_url"].rstrip("/"),
            "model": profile["default_model"],
            "api_key": self._secret({**profile, "secret_ref_id": profile["secret"]["reference_id"]}),
            "timeout": profile["request_timeout_seconds"],
            "is_local": profile["is_local"],
            "config": profile["config"],
        }

    async def health(self, profile_id: str) -> dict[str, Any]:
        profile = self.get(profile_id, include_health=True)
        try:
            ready, message = await self.adapter(profile_id).health()
        except Exception as exc:
            ready, message = False, str(exc)
        message = self.secrets.redact_text(message)[:1000]
        checked = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE provider_profiles SET last_health_ok=?,last_health_message=?,last_checked_at=?,updated_at=? WHERE id=?",
                (int(ready), message, checked, checked, profile_id),
            )
        return {"profile_id": profile_id, "ready": ready, "message": message, "checked_at": checked}
