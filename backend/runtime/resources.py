from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.providers.secrets import SENSITIVE_KEY, SecretStore
from backend.runtime.contracts import (
    DEFAULT_PROFILE_LIMITS,
    MEDIA_CLASSES,
    RESOURCE_PRIORITY,
    ResourceClaim,
    ResourceClass,
    ResourceError,
    ResourceProfile,
    ResourceProfileLimits,
    ResourceRequest,
    ResourceRequestStatus,
)
from backend.storage.database import Database, utc_now


_GROUP_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}:[a-z][a-z0-9_-]{0,63}$")
_OWNER_PART = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")
_FINAL = frozenset({ResourceRequestStatus.COMPLETED, ResourceRequestStatus.FAILED, ResourceRequestStatus.CANCELLED})


def _expires_at(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(timespec="milliseconds")


def _redact(value: Any, secrets: SecretStore | None = None, *, depth: int = 0) -> Any:
    if depth > 8:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {
            str(key): "***" if SENSITIVE_KEY.search(str(key)) else _redact(item, secrets, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item, secrets, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return secrets.redact_text(value) if secrets else value
    return value


class ResourceCoordinator:
    """Persistent, cancellation-safe admission control for optional runtimes.

    It does not start providers or kill running work.  A caller obtains an
    admission, starts its own provider job, heartbeats the leases, then marks
    the request terminal.  This keeps a delayed ComfyUI worker isolated from
    the latency-sensitive voice and chat control paths.
    """

    def __init__(self, database: Database, secrets: SecretStore | None = None) -> None:
        self.database = database
        self.secrets = secrets
        self._changed = asyncio.Event()

    def initialize(self) -> dict[str, Any]:
        """Create the default Balanced policy and expire leases after restart."""
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO resource_settings(id,profile,custom_limits_json,updated_at) VALUES(1,?,?,?)",
                (ResourceProfile.BALANCED.value, "{}", now),
            )
            for name, capacity in DEFAULT_PROFILE_LIMITS[ResourceProfile.BALANCED].groups.items():
                connection.execute(
                    "INSERT OR IGNORE INTO resource_groups(name,capacity_units,enabled,updated_at) VALUES(?,?,1,?)",
                    (name, capacity, now),
                )
        return self.recover_after_restart()

    def settings(self) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM resource_settings WHERE id=1").fetchone()
        if row is None:
            self.initialize()
            return self.settings()
        profile = ResourceProfile(row["profile"])
        custom = json.loads(row["custom_limits_json"])
        limits = self._limits(profile, custom)
        return {"profile": profile.value, "custom_limits": _redact(custom, self.secrets), "effective_limits": limits.as_dict()}

    def update_settings(self, profile: ResourceProfile | str, custom_limits: Mapping[str, Any] | None = None) -> dict[str, Any]:
        selected = ResourceProfile(profile)
        custom = dict(custom_limits or {})
        if self._contains_sensitive_key(custom):
            raise ResourceError("sensitive_limits", "Resource limits cannot contain credentials or secrets")
        if selected is ResourceProfile.CUSTOM:
            self._limits(selected, custom)  # validates before persisting
        elif custom:
            raise ResourceError("profile_limits", "custom_limits are only allowed for the custom profile")
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO resource_settings(id,profile,custom_limits_json,updated_at) VALUES(1,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET profile=excluded.profile,custom_limits_json=excluded.custom_limits_json,updated_at=excluded.updated_at",
                (selected.value, json.dumps(custom, separators=(",", ":")), now),
            )
            limits = self._limits(selected, custom)
            for name, capacity in limits.groups.items():
                connection.execute(
                    "INSERT INTO resource_groups(name,capacity_units,enabled,updated_at) VALUES(?,?,1,?) "
                    "ON CONFLICT(name) DO UPDATE SET capacity_units=excluded.capacity_units,updated_at=excluded.updated_at",
                    (name, capacity, now),
                )
        self._changed.set()
        self.pump()
        return self.settings()

    def list_groups(self) -> list[dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT * FROM resource_groups ORDER BY name").fetchall()
            result = []
            for row in rows:
                used = connection.execute(
                    "SELECT COALESCE(SUM(units),0) FROM resource_leases WHERE resource_group=? AND state='active' AND expires_at>?",
                    (row["name"], utc_now()),
                ).fetchone()[0]
                result.append({"name": row["name"], "capacity_units": row["capacity_units"], "enabled": bool(row["enabled"]),
                               "used_units": used, "available_units": max(0, row["capacity_units"] - used)})
        return result

    def update_group(self, name: str, *, capacity_units: int, enabled: bool = True) -> dict[str, Any]:
        self._validate_group(name)
        if not 1 <= capacity_units <= 100_000:
            raise ResourceError("invalid_group_capacity", "Resource group capacity must be from 1 to 100000")
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO resource_groups(name,capacity_units,enabled,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET capacity_units=excluded.capacity_units,enabled=excluded.enabled,updated_at=excluded.updated_at",
                (name, capacity_units, int(enabled), utc_now()),
            )
        self._changed.set(); self.pump()
        return next(group for group in self.list_groups() if group["name"] == name)

    def submit(
        self,
        *,
        owner_type: str,
        owner_id: str,
        resource_class: ResourceClass | str,
        claims: list[ResourceClaim] | tuple[ResourceClaim, ...],
        session_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ResourceRequest:
        kind = ResourceClass(resource_class)
        self._validate_owner(owner_type, owner_id)
        normalized = self._normalize_claims(claims)
        clean_metadata = self._validate_metadata(metadata or {})
        settings = self.settings()["effective_limits"]
        now = utc_now(); request_id = uuid.uuid4().hex
        with self.database.transaction() as connection:
            queued = connection.execute(
                "SELECT COUNT(*) FROM resource_requests WHERE status IN ('queued','paused','admitted','running')"
            ).fetchone()[0]
            if queued >= int(settings["max_queued_requests"]):
                raise ResourceError("queue_full", "Resource queue is at its configured admission limit")
            if session_id and not connection.execute("SELECT 1 FROM sessions WHERE id=? AND deleted_at IS NULL", (session_id,)).fetchone():
                raise ResourceError("session_not_found", "Session was not found for this resource request")
            connection.execute(
                "INSERT INTO resource_requests(id,owner_type,owner_id,session_id,resource_class,priority,claims_json,metadata_json,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (request_id, owner_type, owner_id, session_id, kind.value, RESOURCE_PRIORITY[kind],
                 json.dumps([{"group": item.group, "units": item.units} for item in normalized], separators=(",", ":")),
                 json.dumps(clean_metadata, ensure_ascii=False, separators=(",", ":")), ResourceRequestStatus.QUEUED.value, now, now),
            )
            self._event(connection, request_id, "resource.queued", {"class": kind.value, "priority": RESOURCE_PRIORITY[kind]})
        self._changed.set()
        self.pump()
        return self.get(request_id)

    def get(self, request_id: str) -> ResourceRequest:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM resource_requests WHERE id=?", (request_id,)).fetchone()
        if row is None:
            raise ResourceError("request_not_found", "Resource request was not found")
        return self._to_request(row)

    def list(self, *, session_id: str | None = None, active_only: bool = False) -> list[ResourceRequest]:
        clauses: list[str] = []; values: list[Any] = []
        if session_id is not None:
            clauses.append("session_id=?"); values.append(session_id)
        if active_only:
            clauses.append("status NOT IN ('completed','failed','cancelled')")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.database.read() as connection:
            rows = connection.execute(f"SELECT * FROM resource_requests{where} ORDER BY priority,created_at,id", values).fetchall()
        return [self._to_request(row) for row in rows]

    def events(self, request_id: str, *, after: int = 0) -> list[dict[str, Any]]:
        self.get(request_id)
        with self.database.read() as connection:
            rows = connection.execute("SELECT * FROM resource_events WHERE request_id=? AND sequence>? ORDER BY sequence", (request_id, after)).fetchall()
        return [{"id": row["id"], "request_id": row["request_id"], "sequence": row["sequence"], "type": row["type"],
                 "payload": _redact(json.loads(row["payload_json"]), self.secrets), "created_at": row["created_at"]} for row in rows]

    def pump(self) -> int:
        """Admit all work currently safe for configured local groups.

        Media work is deliberately paused while any realtime/chat/STT request
        is pending or active.  Existing media is never preempted here.
        """
        admitted = 0
        while self._admit_one():
            admitted += 1
        if admitted:
            self._changed.set()
        return admitted

    def start(self, request_id: str) -> ResourceRequest:
        with self.database.transaction() as connection:
            row = self._request_row(connection, request_id)
            status = ResourceRequestStatus(row["status"])
            if status is ResourceRequestStatus.RUNNING:
                return self._to_request(row)
            if status is not ResourceRequestStatus.ADMITTED:
                raise ResourceError("not_admitted", "Resource request must be admitted before it can run")
            now = utc_now()
            connection.execute("UPDATE resource_requests SET status='running',updated_at=? WHERE id=?", (now, request_id))
            self._event(connection, request_id, "resource.running", {})
        return self.get(request_id)

    def heartbeat(self, request_id: str) -> ResourceRequest:
        request = self.get(request_id)
        if request.status not in {ResourceRequestStatus.ADMITTED, ResourceRequestStatus.RUNNING}:
            raise ResourceError("lease_not_active", "Only admitted or running work can renew a lease")
        ttl = int(self.settings()["effective_limits"]["lease_ttl_seconds"])
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute("UPDATE resource_leases SET heartbeat_at=?,expires_at=? WHERE request_id=? AND state='active'", (now, _expires_at(ttl), request_id))
            connection.execute("UPDATE resource_requests SET updated_at=? WHERE id=?", (now, request_id))
        return self.get(request_id)

    def complete(self, request_id: str) -> ResourceRequest:
        return self._finish(request_id, ResourceRequestStatus.COMPLETED)

    def fail(self, request_id: str, *, error_code: str, error_message: str) -> ResourceRequest:
        return self._finish(request_id, ResourceRequestStatus.FAILED, error_code=error_code, error_message=error_message)

    def cancel(self, request_id: str) -> ResourceRequest:
        with self.database.transaction() as connection:
            row = self._request_row(connection, request_id)
            status = ResourceRequestStatus(row["status"])
            if status in _FINAL:
                return self._to_request(row)
            now = utc_now()
            connection.execute("UPDATE resource_requests SET cancel_requested=1,updated_at=? WHERE id=?", (now, request_id))
            if status is not ResourceRequestStatus.RUNNING:
                connection.execute("UPDATE resource_requests SET status='cancelled',finished_at=?,updated_at=? WHERE id=?", (now, now, request_id))
                self._release(connection, request_id, "cancelled")
                self._event(connection, request_id, "resource.cancelled", {"before_start": True})
            else:
                self._event(connection, request_id, "resource.cancel_requested", {})
        self._changed.set(); self.pump()
        return self.get(request_id)

    def acknowledge_cancel(self, request_id: str) -> ResourceRequest:
        """Release a running request after its owner has actually stopped."""
        request = self.get(request_id)
        if request.status is ResourceRequestStatus.CANCELLED:
            return request
        if not request.cancel_requested:
            raise ResourceError("cancel_not_requested", "Cancellation must be requested before acknowledgement")
        return self._finish(request_id, ResourceRequestStatus.CANCELLED)

    def sweep_expired(self) -> int:
        now = utc_now(); released = 0
        with self.database.transaction() as connection:
            rows = connection.execute("SELECT DISTINCT request_id FROM resource_leases WHERE state='active' AND expires_at<=?", (now,)).fetchall()
            for row in rows:
                request_id = row["request_id"]
                connection.execute("UPDATE resource_leases SET state='expired',released_at=?,release_reason='lease_expired' WHERE request_id=? AND state='active'", (now, request_id))
                request = self._request_row(connection, request_id)
                if request["status"] in {"admitted", "running"}:
                    connection.execute("UPDATE resource_requests SET status='failed',error_code='lease_expired',error_message='Resource lease expired without a heartbeat',finished_at=?,updated_at=? WHERE id=?", (now, now, request_id))
                    self._event(connection, request_id, "resource.lease_expired", {})
                released += 1
        if released:
            self._changed.set(); self.pump()
        return released

    def recover_after_restart(self) -> dict[str, Any]:
        """Release stale process-local leases and persist the recovery decision."""
        now = utc_now(); recovered: list[dict[str, str]] = []
        with self.database.transaction() as connection:
            rows = connection.execute("SELECT * FROM resource_requests WHERE status IN ('admitted','running')").fetchall()
            for row in rows:
                metadata = json.loads(row["metadata_json"])
                requested = str(metadata.get("restart_policy", ""))
                resource_class = ResourceClass(row["resource_class"])
                action = "requeue" if requested == "requeue" or (not requested and resource_class in MEDIA_CLASSES) else "cancel"
                next_status = ResourceRequestStatus.QUEUED.value if action == "requeue" and not row["cancel_requested"] else ResourceRequestStatus.CANCELLED.value
                connection.execute("UPDATE resource_leases SET state='expired',released_at=?,release_reason='backend_restart' WHERE request_id=? AND state='active'", (now, row["id"]))
                connection.execute("UPDATE resource_requests SET status=?,updated_at=?,admitted_at=NULL,finished_at=? WHERE id=?", (next_status, now, now if next_status == "cancelled" else None, row["id"]))
                payload = {"action": action, "previous_status": row["status"], "next_status": next_status}
                self._event(connection, row["id"], "resource.recovered", payload)
                connection.execute("INSERT INTO resource_recovery_events(request_id,action,metadata_json,created_at) VALUES(?,?,?,?)", (row["id"], action, json.dumps(payload, separators=(",", ":")), now))
                recovered.append({"request_id": row["id"], "action": action})
        if recovered:
            self._changed.set(); self.pump()
        return {"recovered": recovered, "count": len(recovered), "at": now}

    async def wait_for_admission(self, request_id: str, *, timeout_seconds: float | None = None) -> ResourceRequest:
        """Optional cancellable waiter for worker adapters; state remains in SQLite."""
        loop = asyncio.get_running_loop(); deadline = None if timeout_seconds is None else loop.time() + timeout_seconds
        while True:
            # Clear before reading the durable state so an update that lands
            # between these operations cannot be missed by the waiter.
            self._changed.clear()
            request = self.get(request_id)
            if request.status in {ResourceRequestStatus.ADMITTED, ResourceRequestStatus.RUNNING, *_FINAL}:
                return request
            remaining = None if deadline is None else deadline - loop.time()
            if remaining is not None and remaining <= 0:
                return request
            try:
                await asyncio.wait_for(self._changed.wait(), timeout=remaining)
            except TimeoutError:
                return self.get(request_id)

    def diagnostics(self, *, dependencies: Mapping[str, Any] | None = None) -> dict[str, Any]:
        with self.database.read() as connection:
            status_rows = connection.execute("SELECT status,COUNT(*) AS count FROM resource_requests GROUP BY status").fetchall()
            recovery_rows = connection.execute("SELECT action,COUNT(*) AS count FROM resource_recovery_events GROUP BY action").fetchall()
        return {
            "settings": self.settings(),
            "groups": self.list_groups(),
            "requests_by_status": {row["status"]: row["count"] for row in status_rows},
            "restart_recovery": {row["action"]: row["count"] for row in recovery_rows},
            "dependencies": _redact(dict(dependencies or {}), self.secrets),
            "redaction": "Secrets and credential-shaped fields are omitted from coordinator diagnostics.",
        }

    def _admit_one(self) -> bool:
        with self.database.transaction() as connection:
            self._expire_in_transaction(connection)
            row = connection.execute("SELECT * FROM resource_requests WHERE status IN ('queued','paused') AND cancel_requested=0 ORDER BY priority,created_at,id LIMIT 1").fetchone()
            if row is None:
                return False
            resource_class = ResourceClass(row["resource_class"])
            if resource_class in MEDIA_CLASSES and self._interactive_demand(connection):
                if row["status"] != ResourceRequestStatus.PAUSED.value:
                    connection.execute("UPDATE resource_requests SET status='paused',updated_at=? WHERE id=?", (utc_now(), row["id"]))
                    self._event(connection, row["id"], "resource.admission_paused", {"reason": "interactive_demand"})
                return False
            if row["status"] == ResourceRequestStatus.PAUSED.value:
                connection.execute("UPDATE resource_requests SET status='queued',updated_at=? WHERE id=?", (utc_now(), row["id"]))
                self._event(connection, row["id"], "resource.resumed", {})
                row = self._request_row(connection, row["id"])
            claims = self._claims_from_json(row["claims_json"])
            limits = self._active_limits_in_transaction(connection)
            active_leases = connection.execute("SELECT COUNT(*) FROM resource_leases WHERE state='active' AND expires_at>?", (utc_now(),)).fetchone()[0]
            if active_leases + len(claims) > limits.max_active_leases or not self._claims_available(connection, claims):
                return False
            now = utc_now()
            for claim in claims:
                connection.execute("INSERT INTO resource_leases(id,request_id,resource_group,units,state,metadata_json,acquired_at,heartbeat_at,expires_at) VALUES(?,?,?,?, 'active',?,?,?,?)",
                                   (uuid.uuid4().hex, row["id"], claim.group, claim.units, "{}", now, now, _expires_at(limits.lease_ttl_seconds)))
            connection.execute("UPDATE resource_requests SET status='admitted',admitted_at=?,updated_at=? WHERE id=?", (now, now, row["id"]))
            self._event(connection, row["id"], "resource.admitted", {"claims": [{"group": item.group, "units": item.units} for item in claims]})
            return True

    def _finish(self, request_id: str, status: ResourceRequestStatus, *, error_code: str | None = None, error_message: str | None = None) -> ResourceRequest:
        with self.database.transaction() as connection:
            row = self._request_row(connection, request_id)
            current = ResourceRequestStatus(row["status"])
            if current in _FINAL:
                return self._to_request(row)
            if current not in {ResourceRequestStatus.ADMITTED, ResourceRequestStatus.RUNNING}:
                raise ResourceError("not_running", "Only admitted or running work can be completed or failed")
            now = utc_now()
            message = self.secrets.redact_text(error_message) if self.secrets and error_message else error_message
            connection.execute("UPDATE resource_requests SET status=?,error_code=?,error_message=?,finished_at=?,updated_at=? WHERE id=?", (status.value, error_code, message, now, now, request_id))
            self._release(connection, request_id, status.value)
            self._event(connection, request_id, f"resource.{status.value}", {"error_code": error_code} if error_code else {})
        self._changed.set(); self.pump()
        return self.get(request_id)

    def _release(self, connection: Any, request_id: str, reason: str) -> None:
        connection.execute("UPDATE resource_leases SET state='released',released_at=?,release_reason=? WHERE request_id=? AND state='active'", (utc_now(), reason, request_id))

    def _event(self, connection: Any, request_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
        sequence = connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM resource_events WHERE request_id=?", (request_id,)).fetchone()[0]
        connection.execute("INSERT INTO resource_events(request_id,sequence,type,payload_json,created_at) VALUES(?,?,?,?,?)", (request_id, sequence, event_type, json.dumps(_redact(dict(payload), self.secrets), ensure_ascii=False, separators=(",", ":")), utc_now()))

    def _request_row(self, connection: Any, request_id: str) -> Any:
        row = connection.execute("SELECT * FROM resource_requests WHERE id=?", (request_id,)).fetchone()
        if row is None:
            raise ResourceError("request_not_found", "Resource request was not found")
        return row

    def _active_limits_in_transaction(self, connection: Any) -> ResourceProfileLimits:
        row = connection.execute("SELECT profile,custom_limits_json FROM resource_settings WHERE id=1").fetchone()
        if row is None:
            raise ResourceError("coordinator_uninitialized", "Resource coordinator must be initialized before admission")
        return self._limits(ResourceProfile(row["profile"]), json.loads(row["custom_limits_json"]))

    def _claims_available(self, connection: Any, claims: tuple[ResourceClaim, ...]) -> bool:
        now = utc_now()
        for claim in claims:
            group = connection.execute("SELECT capacity_units,enabled FROM resource_groups WHERE name=?", (claim.group,)).fetchone()
            if group is None or not group["enabled"]:
                return False
            used = connection.execute("SELECT COALESCE(SUM(units),0) FROM resource_leases WHERE resource_group=? AND state='active' AND expires_at>?", (claim.group, now)).fetchone()[0]
            if int(used) + claim.units > int(group["capacity_units"]):
                return False
        return True

    def _interactive_demand(self, connection: Any) -> bool:
        return bool(connection.execute("SELECT 1 FROM resource_requests WHERE priority<? AND status IN ('queued','paused','admitted','running') AND cancel_requested=0 LIMIT 1", (RESOURCE_PRIORITY[ResourceClass.IMAGE],)).fetchone())

    def _expire_in_transaction(self, connection: Any) -> None:
        now = utc_now()
        expired = connection.execute("SELECT DISTINCT request_id FROM resource_leases WHERE state='active' AND expires_at<=?", (now,)).fetchall()
        for item in expired:
            request_id = item["request_id"]
            connection.execute("UPDATE resource_leases SET state='expired',released_at=?,release_reason='lease_expired' WHERE request_id=? AND state='active'", (now, request_id))
            row = self._request_row(connection, request_id)
            if row["status"] in {"admitted", "running"}:
                connection.execute("UPDATE resource_requests SET status='failed',error_code='lease_expired',error_message='Resource lease expired without a heartbeat',finished_at=?,updated_at=? WHERE id=?", (now, now, request_id))
                self._event(connection, request_id, "resource.lease_expired", {})

    @staticmethod
    def _validate_owner(owner_type: str, owner_id: str) -> None:
        if not _OWNER_PART.fullmatch(owner_type) or not _OWNER_PART.fullmatch(owner_id):
            raise ResourceError("invalid_owner", "Resource owner identifiers contain unsupported characters")

    @staticmethod
    def _validate_group(name: str) -> None:
        if not _GROUP_NAME.fullmatch(name):
            raise ResourceError("invalid_resource_group", "Resource group must look like gpu:local or cpu:local")

    def _normalize_claims(self, claims: list[ResourceClaim] | tuple[ResourceClaim, ...]) -> tuple[ResourceClaim, ...]:
        if not 1 <= len(claims) <= 4:
            raise ResourceError("invalid_claims", "A request must contain from one to four resource claims")
        seen: set[str] = set(); normalized: list[ResourceClaim] = []
        for claim in claims:
            self._validate_group(claim.group)
            if claim.group in seen or not 1 <= int(claim.units) <= 100_000:
                raise ResourceError("invalid_claims", "Claims must use unique groups with positive bounded units")
            seen.add(claim.group); normalized.append(ResourceClaim(claim.group, int(claim.units)))
        return tuple(normalized)

    def _validate_metadata(self, metadata: Mapping[str, Any], *, depth: int = 0) -> dict[str, Any]:
        if depth > 6 or len(metadata) > 64:
            raise ResourceError("invalid_metadata", "Resource metadata is too deeply nested or too large")
        for key, value in metadata.items():
            if SENSITIVE_KEY.search(str(key)):
                raise ResourceError("sensitive_metadata", "Resource metadata cannot contain credentials or secrets")
            if isinstance(value, Mapping):
                self._validate_metadata(value, depth=depth + 1)
            elif isinstance(value, list):
                if len(value) > 64:
                    raise ResourceError("invalid_metadata", "Resource metadata list is too large")
            elif value is not None and not isinstance(value, (str, int, float, bool)):
                raise ResourceError("invalid_metadata", "Resource metadata must be JSON-compatible")
        encoded = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 16_000:
            raise ResourceError("invalid_metadata", "Resource metadata exceeds 16 KB")
        return _redact(dict(metadata), self.secrets)

    @staticmethod
    def _contains_sensitive_key(value: Any) -> bool:
        if isinstance(value, Mapping):
            return any(SENSITIVE_KEY.search(str(key)) or ResourceCoordinator._contains_sensitive_key(item) for key, item in value.items())
        if isinstance(value, (list, tuple)):
            return any(ResourceCoordinator._contains_sensitive_key(item) for item in value)
        return False

    @staticmethod
    def _claims_from_json(raw: str) -> tuple[ResourceClaim, ...]:
        return tuple(ResourceClaim(str(item["group"]), int(item["units"])) for item in json.loads(raw))

    def _to_request(self, row: Any) -> ResourceRequest:
        return ResourceRequest(id=row["id"], owner_type=row["owner_type"], owner_id=row["owner_id"], session_id=row["session_id"],
                               resource_class=ResourceClass(row["resource_class"]), status=ResourceRequestStatus(row["status"]),
                               claims=self._claims_from_json(row["claims_json"]), metadata=_redact(json.loads(row["metadata_json"]), self.secrets),
                               cancel_requested=bool(row["cancel_requested"]), created_at=row["created_at"], updated_at=row["updated_at"],
                               admitted_at=row["admitted_at"], finished_at=row["finished_at"])

    @staticmethod
    def _limits(profile: ResourceProfile, custom: Mapping[str, Any]) -> ResourceProfileLimits:
        if profile is not ResourceProfile.CUSTOM:
            return DEFAULT_PROFILE_LIMITS[profile]
        try:
            groups = {str(name): int(value) for name, value in dict(custom["groups"]).items()}
            limits = ResourceProfileLimits(max_queued_requests=int(custom["max_queued_requests"]), max_active_leases=int(custom["max_active_leases"]), lease_ttl_seconds=int(custom["lease_ttl_seconds"]), groups=groups)
        except (KeyError, TypeError, ValueError) as exc:
            raise ResourceError("invalid_custom_profile", "Custom profile needs queue, lease, TTL and group limits") from exc
        if not 1 <= limits.max_queued_requests <= 100_000 or not 1 <= limits.max_active_leases <= 10_000 or not 15 <= limits.lease_ttl_seconds <= 3_600:
            raise ResourceError("invalid_custom_profile", "Custom limits are outside safe server bounds")
        if not 1 <= len(limits.groups) <= 16:
            raise ResourceError("invalid_custom_profile", "Custom profile needs from one to sixteen groups")
        for name, capacity in limits.groups.items():
            if not _GROUP_NAME.fullmatch(name) or not 1 <= capacity <= 100_000:
                raise ResourceError("invalid_custom_profile", "Custom resource group is invalid")
        return limits
