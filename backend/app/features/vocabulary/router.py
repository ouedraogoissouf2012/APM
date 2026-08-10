from fastapi import APIRouter, Depends, Query

from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.vocabulary.dependencies import get_vocabulary_service
from app.features.vocabulary.schemas import StatusUpdate, VocabularyEntryOut
from app.features.vocabulary.service import VocabularyService

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])


@router.get("", response_model=list[VocabularyEntryOut])
async def list_vocabulary(
    current_user: User = Depends(get_current_user),
    service: VocabularyService = Depends(get_vocabulary_service),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    before_id: int | None = Query(
        None, ge=1, description="Keyset cursor: the last entry id seen; returns the next page."
    ),
) -> list[VocabularyEntryOut]:
    """The learner's vocabulary notebook, newest first. Paginated (keyset): pass
    ``before_id`` = the last entry's id to fetch the next (older) page."""
    entries = await service.list_notebook(current_user.id, limit=limit, before_id=before_id)
    return [VocabularyEntryOut.model_validate(e) for e in entries]


@router.patch("/{entry_id}", response_model=VocabularyEntryOut)
async def update_status(
    entry_id: int,
    payload: StatusUpdate,
    current_user: User = Depends(get_current_user),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> VocabularyEntryOut:
    """Mark a card as 'known' (Je le sais) or back to 'review' (Encore)."""
    entry = await service.mark(entry_id, current_user.id, payload.status)
    return VocabularyEntryOut.model_validate(entry)
