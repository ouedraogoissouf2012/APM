"""Shared bounded, in-memory audio upload parsing (#227, #230).

Every endpoint that accepts a recorded clip (`/transcribe`, `/shadowing/attempt`,
`/minimal-pairs/attempt`) must reject an oversized upload AND never let it touch
disk. FastAPI's plain `audio: UploadFile` parameter goes through Starlette's
default multipart parser, whose `SpooledTemporaryFile` rolls to disk past 1 MB —
well under a real ~40s recorded turn (~1.3 MB) — undercutting the "audio is
processed in memory and never stored on disk" promise (#128). This module is the
one place that gets both guarantees right; extracted from stt_router.py so the
three upload endpoints share it instead of three divergent copies (#230).
"""

from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser


class _InMemoryMultiPartParser(MultiPartParser):
    """A multipart parser that keeps every part in memory instead of spooling it
    to a real temp FILE on disk.

    Raising the spool threshold to the global body cap (already enforced by
    BodySizeLimitMiddleware) keeps anything that reaches the endpoint in the
    in-memory buffer, so a legitimate clip never touches disk.

    Couples to Starlette's internal ``spool_max_size`` / ``max_part_size`` class
    attributes (set per-instance here); revisit on a Starlette upgrade — tracked.
    """

    def __init__(self, *args: object, spool_max_size: int, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        # ints, not floats — SpooledTemporaryFile(max_size=...) expects an int.
        self.spool_max_size = spool_max_size
        self.max_part_size = spool_max_size


async def parse_bounded_multipart(
    request: Request,
    *,
    audio_field: str = "audio",
    max_bytes: int,
    spool_max_size: int,
) -> tuple[bytes, dict[str, str]]:
    """Parse a multipart body in memory, returning the `audio_field` part's bytes
    (bounded, 413 if oversized) plus every other text field.

    Parses the raw request stream directly (like /transcribe), so — unlike a
    plain FastAPI `UploadFile` parameter, which goes through Starlette's default
    parser and spools past 1 MB — nothing here ever touches disk. Because the
    stream is consumed here, any other form fields (e.g. `target_text`) must be
    read from the returned dict, not from a separate `Form(...)` parameter.

    Checks the declared Content-Length first (fast reject before reading), then
    the actual bytes read (the header can be absent or lie).
    """
    declared = request.headers.get("Content-Length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise HTTPException(status_code=413, detail="Audio upload too large")

    parser = _InMemoryMultiPartParser(
        request.headers, request.stream(), spool_max_size=spool_max_size
    )
    try:
        form = await parser.parse()
    except MultiPartException:
        raise HTTPException(status_code=422, detail="Malformed multipart upload") from None

    # NB: the parser yields Starlette's UploadFile, NOT fastapi.UploadFile (a
    # subclass) — this isinstance must be against the Starlette one to match.
    upload = form.get(audio_field)
    if not isinstance(upload, UploadFile):
        raise HTTPException(status_code=422, detail=f"Missing '{audio_field}' file part")
    try:
        data = await upload.read()
    finally:
        await upload.close()
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="Audio upload too large")

    fields = {k: v for k, v in form.multi_items() if k != audio_field and isinstance(v, str)}
    return data, fields


async def read_bounded_audio(
    request: Request,
    *,
    field_name: str,
    max_bytes: int,
    spool_max_size: int,
) -> bytes:
    """Single-field variant (no other form fields to preserve) — used by
    /transcribe, which only ever sends the audio part."""
    data, _ = await parse_bounded_multipart(
        request, audio_field=field_name, max_bytes=max_bytes, spool_max_size=spool_max_size
    )
    return data
