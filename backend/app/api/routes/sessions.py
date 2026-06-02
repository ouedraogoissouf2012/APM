from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.core import quota
from app.core.livekit import build_room_token
from app.database import get_db
from app.models.session import ConversationSession
from app.models.user import User
from app.schemas.session import SessionEndIn, SessionOut, SessionStartIn, SessionStartOut

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/start", response_model=SessionStartOut, status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: SessionStartIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionStartOut:
    settings = get_settings()
    if quota.remaining_minutes(current_user, settings.free_tier_daily_minutes, date.today()) <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Daily free quota exhausted",
        )
    session = ConversationSession(
        user_id=current_user.id,
        mode=payload.mode,
        scenario_id=payload.scenario_id,
        room_name=f"apm-{current_user.id}-{datetime.now(timezone.utc).timestamp():.0f}",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    token = build_room_token(identity=f"user-{current_user.id}", room=session.room_name)
    return SessionStartOut(
        session_id=session.id,
        room_name=session.room_name,
        livekit_token=token,
        livekit_url=settings.livekit_url,
    )


@router.post("/{session_id}/end", response_model=SessionOut)
async def end_session(
    session_id: int,
    payload: SessionEndIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    session = await db.get(ConversationSession, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session.ended_at = datetime.now(timezone.utc)
    session.duration_minutes = payload.duration_minutes
    quota.record_usage(current_user, payload.duration_minutes, date.today())
    await db.commit()
    await db.refresh(session)
    return SessionOut.model_validate(session)
