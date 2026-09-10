from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.agent.contracts import AgentTaskSpec
from backend.agent.orchestrator import AgentOrchestrator
from backend.config import Settings
from backend.models.base import Capability, ProviderError
from backend.providers.registry import ProviderRegistry
from backend.providers.secrets import SecretStore
from backend.runtime.contracts import ResourceClaim, ResourceClass, ResourceError, ResourceProfile
from backend.runtime.resources import ResourceCoordinator
from backend.storage.database import Database


@pytest.fixture
def database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "stage9-16.sqlite3")
    database.initialize()
    return database


@pytest.fixture
def providers(database: Database) -> tuple[ProviderRegistry, SecretStore]:
    secrets = SecretStore()
    settings = Settings(
        database_path=database.path,
        seed_bundled_skills=False,
        openai_api_key="",
        discovery_timeout_seconds=0.05,
    )
    return ProviderRegistry(database, settings, secrets), secrets


def test_provider_secret_is_redacted_and_never_persisted(database: Database, providers) -> None:
    registry, secrets = providers
    profile = registry.create(
        {
            "provider_type": "openai_compatible",
            "title": "Private route",
            "base_url": "http://provider.invalid/v1",
            "default_model": "model-a",
        },
        secret="sk-stage9-secret",
    )

    assert secrets.has(profile["secret"]["reference_id"])
    assert profile["secret"]["configured"] is True
    assert profile["secret"]["masked"]
    assert "sk-stage9-secret" not in json.dumps(profile)
    assert secrets.redact_text("request sk-stage9-secret failed") == "request *** failed"
    with database.read() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM provider_secret_refs WHERE locator LIKE '%sk-stage9-secret%'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM provider_profiles WHERE config_json LIKE '%sk-stage9-secret%'"
        ).fetchone()[0] == 0


def test_provider_profiles_are_isolated_and_disabled_profiles_cannot_create_adapters(providers) -> None:
    registry, _ = providers
    enabled = registry.create(
        {"provider_type": "ollama", "title": "Local A", "base_url": "http://a", "default_model": "a"}
    )
    disabled = registry.create(
        {
            "provider_type": "ollama",
            "title": "Local B",
            "base_url": "http://b",
            "default_model": "b",
            "enabled": False,
        }
    )

    assert registry.get(enabled["id"])["base_url"] == "http://a"
    assert registry.get(disabled["id"])["base_url"] == "http://b"
    with pytest.raises(ProviderError, match="disabled"):
        registry.adapter(disabled["id"])


def test_capability_overrides_route_selection_to_only_enabled_supporting_profile(providers) -> None:
    registry, _ = providers
    first = registry.create(
        {"provider_type": "ollama", "title": "No vision", "base_url": "http://one", "default_model": "same"}
    )
    second = registry.create(
        {"provider_type": "ollama", "title": "Vision", "base_url": "http://two", "default_model": "same"}
    )
    registry.set_capability(first["id"], "same", Capability.VISION_IMAGES, False)
    registry.set_capability(second["id"], "same", Capability.VISION_IMAGES, True)

    selected = registry.select(Capability.VISION_IMAGES, model="same")
    assert selected["id"] == second["id"]
    assert registry.capabilities(second["id"], "same").supports(Capability.VISION_IMAGES)


class _RouteStore:
    def __init__(self, route: dict[str, dict[str, str]]) -> None:
        self.route = route

    def settings(self):
        return {"role_routes": self.route}


class _RouteRegistry:
    def __init__(self, profiles: dict[str, bool]) -> None:
        self.profiles = profiles

    def get(self, profile_id: str, *, include_health: bool = False):
        if profile_id not in self.profiles:
            from backend.storage.repository import NotFoundError

            raise NotFoundError(profile_id)
        return {"id": profile_id, "enabled": self.profiles[profile_id]}


class _RouteGateway:
    def __init__(self, registry) -> None:
        self.registry = registry


class _RouteExecutor:
    def __init__(self, registry) -> None:
        self.gateway = _RouteGateway(registry)


def test_role_route_precedence_and_disabled_route_rejection() -> None:
    store = _RouteStore({"research": {"provider_profile_id": "research-route", "model": "route-model"}})
    orchestrator = AgentOrchestrator(
        store,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        _RouteExecutor(_RouteRegistry({"session-provider": True, "research-route": True, "explicit": True})),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
    )
    spec = AgentTaskSpec("inspect", {}, role="research", provider_profile_id="explicit", model="explicit-model")
    assert orchestrator._resolve_route(spec, {"provider_profile_id": "session-provider", "model": "session-model"}) == (
        "explicit",
        "explicit-model",
    )
    orchestrator.executor.gateway.registry = _RouteRegistry({"research-route": False})
    with pytest.raises(ValueError, match="disabled"):
        orchestrator._resolve_route(AgentTaskSpec("inspect", {}, role="research"), {"provider_profile_id": None, "model": "session-model"})


@pytest.fixture
def resources(database: Database) -> ResourceCoordinator:
    coordinator = ResourceCoordinator(database, SecretStore({"resource-secret": "resource-secret"}))
    coordinator.initialize()
    return coordinator


def submit_resource(
    coordinator: ResourceCoordinator,
    resource_class: ResourceClass,
    *,
    units: int = 1,
    metadata=None,
    group: str = "gpu:local",
):
    return coordinator.submit(
        owner_type="test",
        owner_id=f"owner-{resource_class.value}",
        resource_class=resource_class,
        claims=[ResourceClaim(group, units)],
        metadata=metadata,
    )


def test_resource_priority_admission_and_metadata_redaction(resources: ResourceCoordinator) -> None:
    resources.update_group("gpu:local", capacity_units=1, enabled=False)
    video = submit_resource(resources, ResourceClass.VIDEO, metadata={"note": "resource-secret"})
    image = submit_resource(resources, ResourceClass.IMAGE)
    resources.update_group("gpu:local", capacity_units=1, enabled=True)
    resources.pump()

    assert resources.get(image.id).status.value == "admitted"
    assert resources.get(video.id).status.value == "queued"
    assert resources.get(video.id).metadata == {"note": "***"}
    assert all("resource-secret" not in json.dumps(event) for event in resources.events(video.id))


def test_resource_lease_heartbeat_expiry_and_release(resources: ResourceCoordinator) -> None:
    resources.update_settings(ResourceProfile.CUSTOM, {
        "max_queued_requests": 10,
        "max_active_leases": 4,
        "lease_ttl_seconds": 15,
        "groups": {"gpu:local": 1},
    })
    request = submit_resource(resources, ResourceClass.IMAGE)
    assert request.status.value == "admitted"
    before = resources.get(request.id).updated_at
    renewed = resources.heartbeat(request.id)
    assert renewed.status.value == "admitted"
    assert renewed.updated_at >= before
    with resources.database.transaction() as connection:
        connection.execute("UPDATE resource_leases SET expires_at='2000-01-01T00:00:00+00:00' WHERE request_id=?", (request.id,))
    assert resources.sweep_expired() == 1
    assert resources.get(request.id).status.value == "failed"
    assert resources.get(request.id).finished_at
    assert resources.events(request.id)[-1]["type"] == "resource.lease_expired"


def test_resource_restart_recovery_requeues_media_and_cancels_interactive(resources: ResourceCoordinator) -> None:
    media = submit_resource(resources, ResourceClass.IMAGE, metadata={"restart_policy": "requeue"})
    interactive = submit_resource(resources, ResourceClass.REALTIME_VOICE, group="cpu:local")
    assert media.status.value == "admitted"
    assert interactive.status.value == "admitted"

    report = resources.recover_after_restart()
    assert report["count"] == 2
    # Recovery requeues media, then the coordinator may immediately admit it again.
    assert resources.get(media.id).status.value in {"queued", "admitted"}
    assert resources.get(interactive.id).status.value == "cancelled"
    assert {item["action"] for item in report["recovered"]} == {"requeue", "cancel"}


def test_configured_maximum_resource_limits_are_high_but_bounded(resources: ResourceCoordinator) -> None:
    settings = resources.update_settings(ResourceProfile.MAXIMUM)
    limits = settings["effective_limits"]
    assert limits["max_queued_requests"] >= 50_000
    assert limits["max_active_leases"] >= 4_096
    assert limits["groups"]["gpu:local"] >= 200
    assert limits["groups"]["network:provider"] >= 192

    with pytest.raises(ResourceError, match="safe server bounds"):
        resources.update_settings(ResourceProfile.CUSTOM, {
            "max_queued_requests": 10,
            "max_active_leases": 1,
            "lease_ttl_seconds": 14,
            "groups": {"gpu:local": 1},
        })
