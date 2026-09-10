from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ResourceProfile(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    MAXIMUM = "maximum"
    CUSTOM = "custom"


class ResourceClass(str, Enum):
    REALTIME_VOICE = "realtime_voice"
    CHAT_VISION = "chat_vision"
    STT_TTS = "stt_tts"
    IMAGE = "image"
    VIDEO = "video"


class ResourceRequestStatus(str, Enum):
    QUEUED = "queued"
    PAUSED = "paused"
    ADMITTED = "admitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


RESOURCE_PRIORITY: dict[ResourceClass, int] = {
    ResourceClass.REALTIME_VOICE: 0,
    ResourceClass.CHAT_VISION: 1,
    ResourceClass.STT_TTS: 2,
    ResourceClass.IMAGE: 3,
    ResourceClass.VIDEO: 4,
}

MEDIA_CLASSES = frozenset({ResourceClass.IMAGE, ResourceClass.VIDEO})
INTERACTIVE_CLASSES = frozenset({
    ResourceClass.REALTIME_VOICE,
    ResourceClass.CHAT_VISION,
    ResourceClass.STT_TTS,
})


@dataclass(frozen=True, slots=True)
class ResourceClaim:
    """Units requested from one local resource group.

    Units are deliberately abstract: a group may represent one GPU, a MIG
    partition, a CPU pool, or an external provider concurrency budget.
    """

    group: str
    units: int


@dataclass(frozen=True, slots=True)
class ResourceProfileLimits:
    max_queued_requests: int
    max_active_leases: int
    lease_ttl_seconds: int
    groups: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_PROFILE_LIMITS: dict[ResourceProfile, ResourceProfileLimits] = {
    # The queue/server limits are intentionally generous. GPU admission is
    # still strict, so a burst cannot turn into unbounded local execution.
    ResourceProfile.CONSERVATIVE: ResourceProfileLimits(
        max_queued_requests=10_000,
        max_active_leases=512,
        lease_ttl_seconds=60,
        groups={"gpu:local": 100, "cpu:local": 100, "network:provider": 32},
    ),
    ResourceProfile.BALANCED: ResourceProfileLimits(
        max_queued_requests=25_000,
        max_active_leases=2_048,
        lease_ttl_seconds=90,
        groups={"gpu:local": 100, "cpu:local": 200, "network:provider": 96},
    ),
    ResourceProfile.MAXIMUM: ResourceProfileLimits(
        max_queued_requests=50_000,
        max_active_leases=4_096,
        lease_ttl_seconds=120,
        groups={"gpu:local": 200, "cpu:local": 400, "network:provider": 192},
    ),
}


@dataclass(frozen=True, slots=True)
class ResourceRequest:
    id: str
    owner_type: str
    owner_id: str
    session_id: str | None
    resource_class: ResourceClass
    status: ResourceRequestStatus
    claims: tuple[ResourceClaim, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    cancel_requested: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    admitted_at: str | None = None
    finished_at: str | None = None


class ResourceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
