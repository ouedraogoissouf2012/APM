from fastapi import APIRouter, Depends, status

from app.config import get_settings
from app.domain.exceptions import NotFoundError
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.sessions.dependencies import get_session_service
from app.features.sessions.schemas import (
    ActiveSessionOut,
    SessionHistoryItemOut,
    SessionOut,
    SessionStartIn,
    SessionStartOut,
    TurnOut,
)
from app.features.sessions.service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionHistoryItemOut])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> list[SessionHistoryItemOut]:
    sessions = await service.history(current_user.id)
    return [SessionHistoryItemOut.model_validate(session) for session in sessions]


@router.post("/start", response_model=SessionStartOut, status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: SessionStartIn,
    current_user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> SessionStartOut:
    started = await service.start(
        current_user.id, payload.mode, payload.scenario_id, payload.mission_id
    )
    return SessionStartOut(
        session_id=started.session.id,
        room_name=started.session.room_name,
        livekit_token=started.livekit_token,
        livekit_url=get_settings().livekit_url,
    )


@router.get("/active", response_model=ActiveSessionOut)
async def active_session(
    current_user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> ActiveSessionOut:
    active = await service.active(current_user.id)
    if active is None:
        raise NotFoundError("No active session")
    return ActiveSessionOut(
        session_id=active.session.id,
        mode=active.session.mode,
        scenario_id=active.session.scenario_id,
        turns=[TurnOut(role=t["role"], content=t["content"]) for t in active.turns],
    )


@router.post("/{session_id}/end", response_model=SessionOut)
async def end_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> SessionOut:
    session = await service.end(session_id, current_user.id)
    return SessionOut.model_validate(session)
