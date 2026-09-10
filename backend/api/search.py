from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request


router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/history")
async def search_history(
    request: Request,
    q: str = Query(min_length=1, max_length=300),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    try:
        results = request.app.state.runtime.history_search.search(q, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"query": q, "results": results}
