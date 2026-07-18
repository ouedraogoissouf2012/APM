"""Session-ownership access rule, shared across features.

Loading a session and refusing to reveal whether it exists when it belongs to
another user (404, not 403) was duplicated in sessions, conversation and
debrief; this is the single implementation.
"""

from app.domain.exceptions import NotFoundError
from app.features.sessions.models import ConversationSession
from app.features.sessions.repository import SessionRepository


async def get_owned_session(
    sessions: SessionRepository, session_id: int, user_id: int
) -> ConversationSession:
    session = await sessions.get(session_id)
    if session is None or session.user_id != user_id:
        raise NotFoundError("Session not found")
    return session
