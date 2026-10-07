from typing import Literal
from fastapi import APIRouter, Depends, Query
from app.dependencies import runtime
from app.terminal.history import HISTORY_QUERY_MAX
from app.terminal.models import EventCategory

router = APIRouter(tags=["terminal"])


@router.get("/terminal/history")
async def history(
    limit: int = Query(default=600, ge=1, le=HISTORY_QUERY_MAX),
    range: Literal["1m", "5m", "15m", "1h", "session"] = "session",
    rt=Depends(runtime),
):
    return {
        "session_id": rt.terminal_service.session_id,
        "range": range,
        **rt.terminal_service.history.metadata(),
        "points": [
            p.model_dump(mode="json")
            for p in rt.terminal_service.history.query(limit, range)
        ],
    }


@router.get("/terminal/events")
async def events(
    limit: int = Query(default=100, ge=1, le=500),
    category: EventCategory | None = None,
    rt=Depends(runtime),
):
    return {
        "session_id": rt.terminal_service.session_id,
        "order": "newest-first",
        "max_events": 500,
        "events": [
            e.model_dump(mode="json")
            for e in rt.terminal_service.events(limit, category)
        ],
    }
