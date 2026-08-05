from fastapi import APIRouter, Depends

from app.domain.exceptions import NotFoundError
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.proof.dependencies import get_proof_service
from app.features.proof.schemas import ProofOut
from app.features.proof.service import ProofService

router = APIRouter(prefix="/me/proof", tags=["proof"])


@router.get("/{skill}", response_model=ProofOut)
async def get_proof(
    skill: str,
    current_user: User = Depends(get_current_user),
    service: ProofService = Depends(get_proof_service),
) -> ProofOut:
    """Before/after proof for a skill (scenario): the factual delta between the
    learner's first and latest session on it. 404 when there aren't yet two
    sessions to compare — the client shows a 'keep practising' state, not a
    fabricated result."""
    proof = await service.proof(current_user.id, skill)
    if proof is None:
        raise NotFoundError("Not enough sessions on this skill yet")
    return ProofOut(
        skill=proof.skill,
        baseline_session_id=proof.baseline_session_id,
        latest_session_id=proof.latest_session_id,
        baseline_started_at=proof.baseline_started_at,
        latest_started_at=proof.latest_started_at,
        baseline_cefr=proof.baseline_cefr,
        latest_cefr=proof.latest_cefr,
        resolved=proof.resolved,
        new_or_worse=proof.new_or_worse,
    )
