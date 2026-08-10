"""#227: /transcribe parses the audio upload fully in memory, never to a disk file.

Starlette's default multipart parser rolls a part to a real temp FILE once it
passes 1 MB, so a ~40 s turn (~1.3 MB) transiently hits disk — undercutting the
"never stored on disk" promise of #128. These tests pin the fix by asserting the
SpooledTemporaryFile never rolled (`_rolled is False`), contrasted with the
default parser which does roll.
"""

from collections.abc import AsyncIterator

import pytest
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartParser

from app.features.conversation.stt_router import _InMemoryMultiPartParser

_BOUNDARY = b"----test227"
_BIG = 1_300_000  # ~1.3 MB — above Starlette's 1 MB spool threshold


def _multipart(size: int) -> bytes:
    head = (
        b"--" + _BOUNDARY + b"\r\n"
        b'Content-Disposition: form-data; name="audio"; filename="a.wav"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
    )
    return head + (b"x" * size) + b"\r\n--" + _BOUNDARY + b"--\r\n"


def _headers(body: bytes) -> Headers:
    return Headers(
        {
            "content-type": f"multipart/form-data; boundary={_BOUNDARY.decode()}",
            "content-length": str(len(body)),
        }
    )


async def _stream(body: bytes) -> AsyncIterator[bytes]:
    yield body


@pytest.mark.asyncio
async def test_default_parser_spools_a_large_part_to_disk():
    # Baseline (the bug): Starlette's default parser rolls a >1 MB part to disk.
    body = _multipart(_BIG)
    form = await MultiPartParser(_headers(body), _stream(body)).parse()
    assert form["audio"].file._rolled is True  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_in_memory_parser_keeps_a_large_part_off_disk():
    # #227: the same 1.3 MB part stays entirely in memory with the raised spool cap.
    body = _multipart(_BIG)
    parser = _InMemoryMultiPartParser(
        _headers(body), _stream(body), spool_max_size=12 * 1024 * 1024
    )
    form = await parser.parse()
    upload = form["audio"]
    assert upload.file._rolled is False  # type: ignore[attr-defined]  # never touched disk
    assert len(await upload.read()) == _BIG  # and the bytes are intact
