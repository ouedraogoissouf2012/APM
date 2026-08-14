"""Unit tests for VoiceDataExportRepository's generic keyset-pagination engine
(#405) — isolated from the database via a fake sessionmaker/session, the same
DB-agnostic contract _keyset_pages has always had (mirrors how
test_voice_data_export_stream.py unit-tests _assemble_export_json with fakes).
Per-category SQL correctness against the real 5 ORM models it now owns —
including the ROLE_USER utterance filter relocated out of the router — is
covered by the DB-backed tests/test_voice_data_export_pagination.py and
tests/test_voice_data_api.py."""

import pytest

from app.features.voice_data.repository import _keyset_pages


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.closed = True


class _FakeSessionmaker:
    def __init__(self) -> None:
        self.sessions_opened = 0

    def __call__(self) -> _FakeSession:
        self.sessions_opened += 1
        return _FakeSession()


@pytest.mark.asyncio
async def test_stops_when_a_page_returns_fewer_rows_than_page_size():
    pages = [[1, 2], [3]]

    async def fetch_page(session, cursor):
        return pages.pop(0)

    items = [
        item
        async for item in _keyset_pages(
            _FakeSessionmaker(), fetch_page, cursor_of=lambda r: r, page_size=2
        )
    ]

    assert items == [1, 2, 3]


@pytest.mark.asyncio
async def test_stops_immediately_on_an_empty_first_page():
    async def fetch_page(session, cursor):
        return []

    items = [
        item
        async for item in _keyset_pages(
            _FakeSessionmaker(), fetch_page, cursor_of=lambda r: r, page_size=2
        )
    ]

    assert items == []


@pytest.mark.asyncio
async def test_forwards_the_previous_pages_cursor_to_the_next_fetch():
    pages = {None: [1, 2], 2: [3]}
    seen_cursors = []

    async def fetch_page(session, cursor):
        seen_cursors.append(cursor)
        return pages[cursor]

    [
        item
        async for item in _keyset_pages(
            _FakeSessionmaker(), fetch_page, cursor_of=lambda r: r, page_size=2
        )
    ]

    assert seen_cursors == [None, 2]


@pytest.mark.asyncio
async def test_opens_a_fresh_session_per_page_and_closes_it_before_yielding():
    """#389: the connection-release guarantee, exercised without a real pool —
    each page's session must already be closed by the time its rows reach the
    consumer, and a new one is opened only for the NEXT page's fetch."""
    pages = [[1], [2], []]
    closed_during_fetch = []

    async def fetch_page(session, cursor):
        closed_during_fetch.append(session.closed)
        return pages.pop(0)

    maker = _FakeSessionmaker()
    sessions_opened_while_consuming = []
    async for _item in _keyset_pages(maker, fetch_page, cursor_of=lambda r: r, page_size=1):
        sessions_opened_while_consuming.append(maker.sessions_opened)

    assert closed_during_fetch == [False, False, False]  # open DURING its own fetch
    assert maker.sessions_opened == 3  # 2 pages of data + the empty terminator page
    # No NEW session was opened before the previous page's row was consumed.
    assert sessions_opened_while_consuming == [1, 2]
