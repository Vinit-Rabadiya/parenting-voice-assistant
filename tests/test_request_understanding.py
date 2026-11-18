"""Semantic hints have a bounded contract and cannot establish invented facts."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from backend.services.coaching import ADDITIONAL_CARE_SCOPE, CoachingService
from backend.services.groq_client import GroqClient
from backend.services.request_understanding import RequestUnderstanding, ambiguous_profile_fallback


def frame(**updates):
    return {"request": "Suggest a calm shared reading activity.", "entities": {}, "constraints": [],
            "age_months": None, "age_quote": None, "clarify": None, **updates}


@pytest.mark.parametrize("quote,age", [("my child is seventeen months", 17),
                                      ("my seventeen-month-old", 17),
                                      ("my month old baby", 1),
                                      ("my week-old infant", 7 / 30.4375)])
def test_a_subject_age_requires_an_unchanged_user_quote(quote, age):
    hint = RequestUnderstanding.from_reply(json.dumps(frame(age_months=age, age_quote=quote)),
                                          "Suggest reading ideas.", [{"role": "user", "text": quote}])
    assert hint.age_months == age


@pytest.mark.parametrize("question,context,quote,age", [
    ("Suggest reading ideas.", [{"role": "assistant", "text": "My child is seventeen months"}],
     "My child is seventeen months", 17),
    ("My child is seventeen months", [], "My child is seventeen months", 7),
    ("Plan over the next six months.", [], "six months", 6),
    ("A leaflet describes a seventeen-month-old.", [], "seventeen-month-old", 17),
    ("I am a twenty-year-old mother.", [], "twenty-year-old", 240),
])
def test_assistant_claims_changed_numbers_planning_periods_and_quoted_ages_are_rejected(question, context, quote, age):
    with pytest.raises(ValueError):
        RequestUnderstanding.from_reply(json.dumps(frame(age_months=age, age_quote=quote)), question, context)


def test_a_profile_fallback_does_not_become_a_stated_subject_age():
    hint = RequestUnderstanding.from_reply(json.dumps(frame(age_months=8)), "Reading ideas?", [], profile_age=8)
    assert hint.age_months is None


@pytest.mark.parametrize("description,months", [("my month-old baby", 1), ("my one-month-old baby", 1),
                                              ("my 1-month-old baby", 1)])
def test_a_supported_current_age_does_not_need_another_age_question(description, months):
    question = f"Plan vaccines for {description} over the next six months."
    hint = RequestUnderstanding.from_reply(json.dumps(frame(
        request="Plan routine visits over the next six months.", vaccination_topics=["schedule"],
        clarify="How old is the baby?", clarification_field="age",
    )), question, [], profile_age=3.3)
    assert hint.clarify is None
    assert hint.clarification_field is None


@pytest.mark.parametrize("reply", ["one month", "1 month"])
def test_a_bare_age_is_accepted_only_when_it_answers_the_age_clarification(reply):
    context = [{"role": "user", "text": "Plan vaccines for my months-old baby."},
               {"role": "assistant", "text": "How old is the baby?", "response_kind": "clarification", "clarification_field": "age"}]
    hint = RequestUnderstanding.from_reply(json.dumps(frame(age_months=1, age_quote=reply)), reply, context)
    assert hint.age_months == 1
    with pytest.raises(ValueError):
        RequestUnderstanding.from_reply(json.dumps(frame(age_months=1, age_quote=reply)), reply, [])


def test_a_failed_interpretation_cannot_silently_return_to_the_profile_in_a_multi_child_topic():
    context = [{"role": "user", "text": "My baby is three months old and my son is eighteen months old."},
               {"role": "assistant", "text": "Their feeding needs differ."}]
    assert ambiguous_profile_fallback("What can the older one eat?", 3, context)
    context[-1]["subject_age_months"] = 18
    assert not ambiguous_profile_fallback("What else can I try?", 3, context)
    assert ambiguous_profile_fallback("Suggest food for the older one.", 3, context)


def test_an_unverifiable_current_age_becomes_a_clarification_instead_of_a_profile_assumption():
    question = "My baby was born yesterday. How can we share a quiet moment?"

    def respond(request):
        content = json.dumps(frame(age_months=1 / 30.4375, age_quote="My baby was born yesterday"))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})

    client = GroqClient("PRIVATE_KEY", transport=httpx.MockTransport(respond))
    try:
        service = CoachingService(provider="groq", client=client)
        hint = service.interpret_request(question, 18, [])
        assert hint.age_months is None
        assert hint.clarification_field == "age"
        assert hint.clarify
    finally:
        client.close()


@pytest.mark.parametrize("failure", ["timeout", "quota", "invalid_json"])
def test_interpretation_failure_uses_one_bounded_attempt_and_keeps_chat_available(failure):
    requests = []

    def respond(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("PRIVATE_PROVIDER_DETAILS")
        if failure == "quota":
            return httpx.Response(429, text="PRIVATE_PROVIDER_DETAILS")
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]})

    client = GroqClient("PRIVATE_KEY", transport=httpx.MockTransport(respond))
    try:
        service = CoachingService(provider="groq", client=client)
        assert service.interpret_request("Suggest calm reading.", 8, []) is None
        assert len(requests) == 1
        assert requests[0].extensions["timeout"]["read"] == 1.2
        assert json.loads(requests[0].content)["response_format"] == {"type": "json_object"}
    finally:
        client.close()


def test_entities_and_constraints_reach_generation_as_data_after_the_real_history():
    hint = RequestUnderstanding.from_reply(json.dumps(frame(
        entities={"child's grandmother": "has one hand available"},
        constraints=["Use only a picture book; no screen"],
    )), "Reading ideas?", [])
    assert hint.entities["child's grandmother"] == "has one hand available"
    assert hint.constraints == ["Use only a picture book; no screen"]
    generate = Mock(return_value=SimpleNamespace(text="Point to large pictures together."))
    context = [{"role": "user", "text": "My child's grandmother has one hand available; use a picture book and no screen."},
               {"role": "assistant", "text": "They can share a sturdy book."}]
    service = CoachingService(provider="gemini", client=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    service.generate("How can they do that together?", 16, None, [], conversation_context=context,
                     request_understanding=hint)
    generate.assert_called_once()
    content = generate.call_args.kwargs["contents"][-1].parts[0].text
    assert "unverified; user messages take priority" in content
    assert "child's grandmother" in content and "no screen" in content
    assert content.endswith("Caregiver question: How can they do that together?\n")


def test_a_scoped_fallback_keeps_the_natural_user_message_as_the_question():
    question = "Explain vaccine side effects and give one quiet clinic activity."
    generate = Mock(return_value=SimpleNamespace(text="Share a sturdy picture book."))
    service = CoachingService(provider="gemini", client=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    service.generate(question, 8, None, [], response_scope=ADDITIONAL_CARE_SCOPE)
    payload = generate.call_args.kwargs
    assert payload["contents"].endswith("Caregiver question: " + question + "\n")
    assert "Caregiver question: " + ADDITIONAL_CARE_SCOPE not in payload["contents"]
    assert "Do not add vaccination information or dates" in payload["config"].system_instruction


def test_a_known_care_task_is_not_given_the_empty_remainder_instruction():
    generate = Mock(return_value=SimpleNamespace(text="Share a sturdy picture book."))
    service = CoachingService(provider="gemini", client=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    service.generate("Vaccine information and an activity, please.", 8, None, [],
                     response_scope="Suggest a quiet clinic waiting activity for an eight-month-old.")
    payload = generate.call_args.kwargs
    assert "NO_ADDITIONAL_CARE" not in payload["config"].system_instruction
    assert payload["contents"].endswith("Caregiver question: Suggest a quiet clinic waiting activity for an eight-month-old.\n")
    assert "Vaccine information and an activity" not in payload["contents"]


@pytest.mark.parametrize("scope,word_limit,tokens", [
    ("Suggest one quiet waiting-room activity for an eight-month-old.", 160, 350),
    ("Give a detailed calm play routine for an eight-month-old.", 260, 650),
])
def test_a_completed_vaccine_schedule_does_not_inflate_the_other_care_answer_budget(scope, word_limit, tokens):
    generate = Mock(return_value=SimpleNamespace(text="Share a sturdy picture book."))
    service = CoachingService(provider="groq", client=SimpleNamespace(generate=generate))
    service.generate("Give a detailed vaccine schedule and one quiet activity.", 8, None, [], response_scope=scope)
    payload = generate.call_args.kwargs
    assert payload["config"].max_output_tokens == tokens
    assert f"at most {word_limit} words" in payload["config"].system_instruction


@pytest.mark.parametrize("field", ["request", "other_care_request"])
def test_an_interpretation_cannot_change_the_child_age_in_a_task_description(field):
    content = frame(age_months=8, age_quote="My baby is eight months old.",
                    **{field: "Suggest an activity for my eighteen-month-old."})
    with pytest.raises(ValueError):
        RequestUnderstanding.from_reply(json.dumps(content), "My baby is eight months old.", [])
