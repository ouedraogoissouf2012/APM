"""Server-side text-to-speech providers.

The reply is synthesized to audio on the backend and streamed to the client, so
the key/endpoint never touches the device and web + mobile behave identically.

`edge` uses Microsoft Edge's read-aloud neural voices (same quality as Azure
Neural TTS) with NO API key, NO account, NO card — ideal for a $0 upgrade over
the robotic on-device system voice. It relies on an unofficial endpoint: great
for MVP/testing; swap for Piper (fully local) or a paid provider for production
via the same TtsProvider seam.
"""

import asyncio

from app.domain.exceptions import LlmProviderError

# Default neural voices per BCP-47 accent tag. The "Multilingual" voices are
# Azure's newest and most natural/expressive — noticeably warmer and less flat
# than the older ...Neural voices, which matters for a conversation partner.
_VOICE_BY_TAG = {
    "en-us": "en-US-AvaMultilingualNeural",
    "en-gb": "en-GB-SoniaNeural",
}
_DEFAULT_VOICE = "en-US-AvaMultilingualNeural"

# edge-tts talks to an UNOFFICIAL Microsoft endpoint — no key, no SLA, and
# nothing previously stopped a hung connection from blocking a turn indefinitely
# (#230). Bounded here (contained to this file); injectable for tests.
_DEFAULT_TIMEOUT_SECONDS = 10.0


def voice_for_language(language_tag: str) -> str:
    return _VOICE_BY_TAG.get(language_tag.lower().replace("_", "-"), _DEFAULT_VOICE)


class EdgeTtsProvider:
    """Neural TTS via Microsoft Edge's free read-aloud voices (no key)."""

    def __init__(
        self, voice: str = _DEFAULT_VOICE, timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        self._voice = voice
        self._timeout_seconds = timeout_seconds

    async def synthesize(self, text: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(text, self._voice)

        async def _collect() -> bytes:
            buffer = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buffer.extend(chunk["data"])
            return bytes(buffer)

        try:
            return await asyncio.wait_for(_collect(), timeout=self._timeout_seconds)
        except Exception as exc:  # network / endpoint failure OR timeout (#230)
            raise LlmProviderError("TTS synthesis failed") from exc
