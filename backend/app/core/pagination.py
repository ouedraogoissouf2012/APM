"""Bounded list pagination (#233).

Every user-facing list query must cap how many rows it can load, so a notebook,
history or schedule that grows for months can never fetch an entire table into
memory. This mirrors the session-history cap already enforced by SessionService.

`resolve_limit` is the shared clamp. Keyset (id-based) cursors live in the
repositories that expose a browsable list (`before_id`): keyset over OFFSET so a
deep page stays O(page), not O(offset).
"""

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


def resolve_limit(
    requested: int | None,
    *,
    default: int = DEFAULT_PAGE_SIZE,
    maximum: int = MAX_PAGE_SIZE,
) -> int:
    """Clamp a requested page size to ``[1, maximum]``, defaulting when unset.

    Defense-in-depth: the API layer validates the query param too, but the
    service must never be able to issue an unbounded query even when called
    directly (tests, future internal callers).
    """
    if requested is None:
        return default
    return max(1, min(requested, maximum))
