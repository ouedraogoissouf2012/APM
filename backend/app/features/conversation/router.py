from fastapi import APIRouter, Depends

from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.conversation.dependencies import get_conversation_turn_service
from app.features.conversation.schemas import TurnIn, TurnOut
from app.features.conversation.turn_service import ConversationTurnService

router = APIRouter(prefix="/sessions/{session_id}", tags=["conversation"])


@router.post("/turn", response_model=TurnOut)
async def take_turn(
    session_id: int,
    payload: TurnIn,
    current_user: User = Depends(get_current_user),
    service: ConversationTurnService = Depends(get_conversation_turn_service),
) -> TurnOut:
    result = await service.take_turn(session_id, current_user, payload.text)
    return TurnOut(reply=result.reply)
