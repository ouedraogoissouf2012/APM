from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_session_service
from app.config import get_settings
from app.models.user import User
from app.schemas.session import SessionOut, SessionStartIn, SessionStartOut
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/start", response_model=SessionStartOut, status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: SessionStartIn,
    current_user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> SessionStartOut:
    started = await service.start(current_user.id, payload.mode, payload.scenario_id)
    return SessionStartOut(
        session_id=started.session.id,
        room_name=started.session.room_name,
        livekit_token=started.livekit_token,
        livekit_url=get_settings().livekit_url,
    )


@router.post("/{session_id}/end", response_model=SessionOut)
async def end_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> SessionOut:
    session = await service.end(session_id, current_user.id)
    return SessionOut.model_validate(session)
