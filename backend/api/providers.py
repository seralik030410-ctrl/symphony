from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response, status

from backend.api.schemas import ProviderProfileCreate, ProviderProfileUpdate
from backend.models.base import Capability, ProviderError
from backend.providers.secrets import SENSITIVE_KEY
from backend.storage.repository import ConflictError, NotFoundError


router = APIRouter(prefix="/api/providers", tags=["providers"])


def _runtime(request: Request):
    return request.app.state.runtime


def _validate_url(value: str) -> None:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise HTTPException(422, "Provider URL must be an HTTP(S) URL without embedded credentials, query or fragment")


def _validate_config(value: Any) -> None:
    if isinstance(value, dict):
        if any(SENSITIVE_KEY.search(str(key)) for key in value):
            raise HTTPException(422, "Provider config cannot contain secrets; use a secret reference")
        for item in value.values():
            _validate_config(item)
    elif isinstance(value, list):
        for item in value:
            _validate_config(item)


def _failure(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(404, str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(409, str(exc))
    if isinstance(exc, (ProviderError, ValueError)):
        return HTTPException(422, str(exc))
    return HTTPException(400, "Provider profile could not be saved")


@router.get("")
async def list_provider_profiles(request: Request) -> list[dict[str, Any]]:
    return _runtime(request).providers.list()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_provider_profile(payload: ProviderProfileCreate, request: Request) -> dict[str, Any]:
    _validate_url(payload.base_url)
    _validate_config(payload.config)
    if payload.secret and payload.secret_env_var:
        raise HTTPException(422, "Choose either a desktop secret or an environment variable")
    try:
        values = payload.model_dump(exclude={"secret"})
        return _runtime(request).providers.create(values, secret=payload.secret)
    except Exception as exc:
        raise _failure(exc) from exc


@router.patch("/{profile_id}")
async def update_provider_profile(profile_id: str, payload: ProviderProfileUpdate, request: Request) -> dict[str, Any]:
    if payload.base_url is not None:
        _validate_url(payload.base_url)
    if payload.config is not None:
        _validate_config(payload.config)
    if (payload.secret and payload.secret_env_var) or (payload.clear_secret and (payload.secret or payload.secret_env_var)):
        raise HTTPException(422, "Secret update options are mutually exclusive")
    try:
        values = payload.model_dump(exclude_unset=True, exclude={"secret", "clear_secret"})
        return _runtime(request).providers.update(
            profile_id, values, secret=payload.secret, clear_secret=payload.clear_secret
        )
    except Exception as exc:
        raise _failure(exc) from exc


@router.delete("/{profile_id}", status_code=204)
async def delete_provider_profile(profile_id: str, request: Request):
    try:
        _runtime(request).providers.delete(profile_id)
        return Response(status_code=204)
    except Exception as exc:
        raise _failure(exc) from exc


@router.post("/{profile_id}/health")
async def check_provider_profile(profile_id: str, request: Request) -> dict[str, Any]:
    try:
        return await _runtime(request).providers.health(profile_id)
    except Exception as exc:
        raise _failure(exc) from exc


@router.get("/{profile_id}/capabilities")
async def provider_capabilities(profile_id: str, model: str, request: Request) -> dict[str, Any]:
    try:
        capabilities = _runtime(request).providers.capabilities(profile_id, model)
        return {"profile_id": profile_id, "model": model, "capabilities": capabilities.capability_map()}
    except Exception as exc:
        raise _failure(exc) from exc


@router.put("/{profile_id}/capabilities/{capability:path}")
async def set_provider_capability(profile_id: str, capability: str, enabled: bool, model: str, request: Request) -> dict[str, Any]:
    try:
        Capability(capability)
        _runtime(request).providers.set_capability(profile_id, model, capability, enabled)
        return {"profile_id": profile_id, "model": model, "capability": capability, "enabled": enabled}
    except Exception as exc:
        raise _failure(exc) from exc
