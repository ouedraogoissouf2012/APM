"""Imports every ORM model so they register on Base.metadata."""

from app.database import Base
from app.features.auth.models import RefreshToken, User
from app.features.conversation.models import Transcript
from app.features.debrief.models import Debrief
from app.features.missions.models import Mission
from app.features.profile.models import LearnerProfile
from app.features.review.models import ReviewItem
from app.features.sessions.models import ConversationSession
from app.features.vocabulary.models import VocabularyEntry
from app.features.voice_consent.models import VoiceConsent

__all__ = [
    "Base",
    "User",
    "RefreshToken",
    "LearnerProfile",
    "ConversationSession",
    "Transcript",
    "Debrief",
    "Mission",
    "VocabularyEntry",
    "ReviewItem",
    "VoiceConsent",
]
