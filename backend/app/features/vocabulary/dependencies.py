from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.features.vocabulary.repository import SqlAlchemyVocabularyRepository
from app.features.vocabulary.service import VocabularyService


def get_vocabulary_service(db: AsyncSession = Depends(get_db)) -> VocabularyService:
    return VocabularyService(SqlAlchemyVocabularyRepository(db))
