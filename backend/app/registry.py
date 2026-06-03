"""Imports every ORM model so they register on Base.metadata.

Used by Alembic (migrations/env.py) for autogenerate and by tests for
create_all. Add a new feature's models here when you create them.
"""

from app.database import Base
from app.features.auth.models import RefreshToken, User
from app.features.profile.models import LearnerProfile
from app.features.sessions.models import ConversationSession

__all__ = ["Base", "User", "RefreshToken", "LearnerProfile", "ConversationSession"]
