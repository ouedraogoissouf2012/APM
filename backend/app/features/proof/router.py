from fastapi import APIRouter, Depends

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
    learner's first and latest session on it. 200 + insufficient_data when there
    aren't yet two sessions to compare (#443) — 404 is reserved for a missing
    resource, not an empty state."""
    proof = await service.proof(current_user.id, skill)
    if proof is None:
        return ProofOut(skill=skill, insufficient_data=True)
    return ProofOut(
        skill=proof.skill,
        baseline_session_id=proof.baseline_session_id,
        latest_session_id=proof.latest_session_id,
        baseline_started_at=proof.baseline_started_at,
        latest_started_at=proof.latest_started_at,
        baseline_cefr=proof.baseline_cefr,
        latest_cefr=proof.latest_cefr,
        baseline_turns=proof.baseline_turns,
        latest_turns=proof.latest_turns,
        resolved=proof.resolved,
        improved=proof.improved,
        new_or_worse=proof.new_or_worse,
    )
