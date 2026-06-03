from app.features.conversation.messages import Message, Transcript


def test_transcript_records_turns_in_order():
    t = Transcript()
    t.add_user("hello")
    t.add_assistant("hi, how are you?")
    assert t.messages == [
        Message(role="user", content="hello"),
        Message(role="assistant", content="hi, how are you?"),
    ]


def test_transcript_to_dicts_for_persistence():
    t = Transcript()
    t.add_user("hello")
    assert t.to_dicts() == [{"role": "user", "content": "hello"}]


def test_transcript_is_empty_initially():
    assert Transcript().messages == []
