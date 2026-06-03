from app.features.conversation.prompt import PromptContext, build_system_prompt


def test_prompt_includes_level_and_no_inline_correction_rule():
    prompt = build_system_prompt(
        PromptContext(cefr_level="A2", scenario_id=None, interests=[], memory_summary="")
    )
    assert "A2" in prompt
    assert "do not correct" in prompt.lower()
    assert "ask" in prompt.lower()


def test_prompt_includes_scenario_role_when_given():
    prompt = build_system_prompt(
        PromptContext(
            cefr_level="B1", scenario_id="restaurant", interests=["food"], memory_summary=""
        )
    )
    assert "restaurant" in prompt.lower()


def test_prompt_weaves_in_memory_summary():
    prompt = build_system_prompt(
        PromptContext(
            cefr_level="B1",
            scenario_id=None,
            interests=[],
            memory_summary="Last time we discussed the user's trip to Italy.",
        )
    )
    assert "Italy" in prompt
