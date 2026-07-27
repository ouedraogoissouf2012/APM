"""Server-side text-to-speech providers.

The reply is synthesized to audio on the backend and streamed to the client, so
the key/endpoint never touches the device and web + mobile behave identically.

`edge` uses Microsoft Edge's read-aloud neural voices (same quality as Azure
Neural TTS) with NO API key, NO account, NO card — ideal for a $0 upgrade over
the robotic on-device system voice. It relies on an unofficial endpoint: great
for MVP/testing; swap for Piper (fully local) or a paid provider for production
via the same TtsProvider seam.
"""

from app.domain.exceptions import LlmProviderError

# Default neural voices per BCP-47 accent tag. The "Multilingual" voices are
# Azure's newest and most natural/expressive — noticeably warmer and less flat
# than the older ...Neural voices, which matters for a conversation partner.
_VOICE_BY_TAG = {
    "en-us": "en-US-AvaMultilingualNeural",
    "en-gb": "en-GB-SoniaNeural",
}
_DEFAULT_VOICE = "en-US-AvaMultilingualNeural"


def voice_for_language(language_tag: str) -> str:
    return _VOICE_BY_TAG.get(language_tag.lower().replace("_", "-"), _DEFAULT_VOICE)


class EdgeTtsProvider:
    """Neural TTS via Microsoft Edge's free read-aloud voices (no key)."""

    def __init__(self, voice: str = _DEFAULT_VOICE) -> None:
        self._voice = voice

    async def synthesize(self, text: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(text, self._voice)
        buffer = bytearray()
        try:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buffer.extend(chunk["data"])
        except Exception as exc:  # network / endpoint failure
            raise LlmProviderError("TTS synthesis failed") from exc
        return bytes(buffer)
