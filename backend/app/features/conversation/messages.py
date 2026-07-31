from dataclasses import dataclass

# Conversation roles — the single source for the "user"/"assistant" protocol
# strings shared by transcripts, prompts and the debrief analyzer.
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"


@dataclass(frozen=True)
class Message:
    role: str  # ROLE_USER | ROLE_ASSISTANT
    content: str
