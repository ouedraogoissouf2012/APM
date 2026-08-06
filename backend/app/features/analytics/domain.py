"""Product analytics primitives (#129).

Privacy by construction: an event carries a name, the pseudonymous user id (an
int, never the email), and a small `properties` dict of STRUCTURED metadata only
— never transcript content or any free-text the learner spoke. This keeps
analytics consistent with the voice policy (#128).
"""

from dataclasses import dataclass, field
from typing import Protocol

# The event names we emit. Kept as a closed set of constants so a typo can't
# silently create a new event stream.
EVENT_ACTIVATION = "activation"  # the user's FIRST completed session
EVENT_SESSION_COMPLETED = "session_completed"  # a session reached its debrief
EVENT_TRANSFER_STARTED = "transfer_started"  # a surprise-transfer challenge began


@dataclass(frozen=True)
class AnalyticsEvent:
    name: str
    user_id: int
    properties: dict = field(default_factory=dict)


class AnalyticsSink(Protocol):
    async def emit(self, event: AnalyticsEvent) -> None:
        """Record an event. Best-effort by contract: analytics must never break
        the feature that produced the event."""
        ...
