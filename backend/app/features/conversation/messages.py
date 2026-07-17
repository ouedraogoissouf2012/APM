from dataclasses import dataclass, field

# Conversation roles — the single source for the "user"/"assistant" protocol
# strings shared by transcripts, prompts and the debrief analyzer.
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"


@dataclass(frozen=True)
class Message:
    role: str  # ROLE_USER | ROLE_ASSISTANT
    content: str


@dataclass
class Transcript:
    messages: list[Message] = field(default_factory=list)

    def add_user(self, content: str) -> None:
        self.messages.append(Message(role=ROLE_USER, content=content))

    def add_assistant(self, content: str) -> None:
        self.messages.append(Message(role=ROLE_ASSISTANT, content=content))

    def to_dicts(self) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.messages]
