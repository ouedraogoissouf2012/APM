from datetime import timedelta
from typing import Protocol

from livekit import api

from app.config import get_settings


class RoomTokenIssuer(Protocol):
    """Issues a join token for a conversation room (DIP seam for services)."""

    def issue(self, identity: str, room: str) -> str: ...


class LiveKitRoomTokenIssuer:
    def issue(self, identity: str, room: str) -> str:
        return build_room_token(identity=identity, room=room)


def build_room_token(identity: str, room: str) -> str:
    settings = get_settings()
    grants = api.VideoGrants(room_join=True, room=room)
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(grants)
        .with_ttl(timedelta(seconds=settings.livekit_token_ttl_seconds))
    )
    return token.to_jwt()
