"""OpenAI sampling parameters are honored, not silently dropped (issue #161).

`ChatCompletionRequest` declared six fields and set `extra="ignore"`, so a client
asking for bounded, deterministic, or JSON-shaped output got a 200 and none of it.
"""

from __future__ import annotations

import pytest

from daari.gateway.sampling import SamplingParams


class TestOllamaMapping:
    def test_max_tokens_becomes_num_predict(self):
        options = SamplingParams(max_tokens=64).ollama_options()
        assert options["num_predict"] == 64

    def test_top_p_seed_and_stop_pass_through(self):
        params = SamplingParams(top_p=0.1, seed=42, stop=["\n\n", "END"])
        options = params.ollama_options()
        assert options["top_p"] == 0.1
        assert options["seed"] == 42
        assert options["stop"] == ["\n\n", "END"]

    def test_unset_parameters_are_absent_rather_than_null(self):
        """Sending nulls would override Ollama's own defaults."""
        assert SamplingParams().ollama_options() == {}

    def test_frequency_penalty_is_translated_to_repeat_penalty(self):
        """The scales differ: OpenAI centres on 0, Ollama on 1.0."""
        assert SamplingParams(frequency_penalty=0.0).ollama_options()["repeat_penalty"] == 1.0
        assert SamplingParams(frequency_penalty=2.0).ollama_options()["repeat_penalty"] == 2.0
        assert SamplingParams(frequency_penalty=-2.0).ollama_options()["repeat_penalty"] == 0.0

    def test_json_response_format_becomes_the_format_field_not_an_option(self):
        params = SamplingParams(response_format_json=True)
        assert params.ollama_format() == "json"
        assert "format" not in params.ollama_options()

    def test_no_format_when_json_was_not_requested(self):
        assert SamplingParams().ollama_format() is None


class TestOpenAIPassthrough:
    def test_supported_parameters_reach_a_frontier_payload(self):
        params = SamplingParams(
            max_tokens=100, top_p=0.5, seed=7, stop=["X"], presence_penalty=0.5
        )
        payload = params.openai_payload()
        assert payload == {
            "max_tokens": 100,
            "top_p": 0.5,
            "seed": 7,
            "stop": ["X"],
            "presence_penalty": 0.5,
        }

    def test_json_mode_is_expressed_in_openai_shape(self):
        payload = SamplingParams(response_format_json=True).openai_payload()
        assert payload["response_format"] == {"type": "json_object"}

    def test_nothing_is_sent_when_nothing_was_asked_for(self):
        assert SamplingParams().openai_payload() == {}

    def test_reasoning_effort_reaches_openai_payload(self):
        payload = SamplingParams(reasoning_effort="high").openai_payload()
        assert payload["reasoning_effort"] == "high"


class TestReasoningEffort:
    """OpenAI reasoning_effort → frontier passthrough + Ollama think (#297)."""

    def test_from_openai_body_keeps_effort(self):
        params = SamplingParams.from_openai_body({"reasoning_effort": "medium"})
        assert params.reasoning_effort == "medium"

    def test_invalid_effort_shapes_are_dropped(self):
        assert SamplingParams.from_openai_body({"reasoning_effort": 3}).reasoning_effort is None
        assert SamplingParams.from_openai_body({"reasoning_effort": ""}).reasoning_effort is None

    def test_ollama_think_mapping(self):
        # minimal → omit (lowest / no explicit think); low/medium/high map 1:1.
        assert SamplingParams(reasoning_effort="minimal").ollama_think() is None
        assert SamplingParams(reasoning_effort="low").ollama_think() == "low"
        assert SamplingParams(reasoning_effort="medium").ollama_think() == "medium"
        assert SamplingParams(reasoning_effort="high").ollama_think() == "high"

    def test_unknown_effort_string_is_omitted_from_think(self):
        assert SamplingParams(reasoning_effort="ultra").ollama_think() is None

    def test_effort_splits_the_cache(self):
        assert (
            SamplingParams(reasoning_effort="low").cache_fingerprint()
            != SamplingParams(reasoning_effort="high").cache_fingerprint()
        )

    def test_effort_does_not_warn_locally(self):
        # Models without thinking support ignore silently (AC3).
        assert SamplingParams(reasoning_effort="high").unsupported_locally() == []

    def test_model_supports_thinking_heuristic(self):
        from daari.gateway.sampling import model_supports_thinking

        assert model_supports_thinking("gpt-oss:20b")
        assert model_supports_thinking("qwen3:8b")
        assert model_supports_thinking("deepseek-r1:thinking")
        assert not model_supports_thinking("llama3.2:3b")


class TestWarnings:
    def test_presence_penalty_warns_on_a_local_model(self):
        """Ollama has no presence_penalty, so silence would be a lie."""
        warnings = SamplingParams(presence_penalty=0.7).unsupported_locally()
        assert any("presence_penalty" in warning for warning in warnings)

    def test_multiple_choices_warn(self):
        assert any("n" == w.split()[0] for w in SamplingParams(n=3).unsupported_locally())

    def test_logprobs_warn(self):
        assert any("logprobs" in w for w in SamplingParams(logprobs=True).unsupported_locally())

    def test_required_tool_choice_warns(self):
        warnings = SamplingParams(tool_choice="required").unsupported_locally()
        assert any("tool_choice" in warning for warning in warnings)

    def test_honored_parameters_do_not_warn(self):
        params = SamplingParams(max_tokens=10, top_p=0.5, seed=1, stop=["a"])
        assert params.unsupported_locally() == []

    def test_n_of_one_is_not_a_warning(self):
        assert SamplingParams(n=1).unsupported_locally() == []


class TestCacheFingerprint:
    def test_different_seeds_do_not_share_a_fingerprint(self):
        assert (
            SamplingParams(seed=1).cache_fingerprint()
            != SamplingParams(seed=2).cache_fingerprint()
        )

    def test_different_max_tokens_do_not_share_a_fingerprint(self):
        assert (
            SamplingParams(max_tokens=10).cache_fingerprint()
            != SamplingParams(max_tokens=100).cache_fingerprint()
        )

    def test_equivalent_params_share_a_fingerprint(self):
        assert (
            SamplingParams(max_tokens=10, top_p=0.5).cache_fingerprint()
            == SamplingParams(top_p=0.5, max_tokens=10).cache_fingerprint()
        )

    def test_empty_params_fingerprint_is_stable_and_empty(self):
        """Requests that ask for nothing must keep hitting pre-#161 entries."""
        assert SamplingParams().cache_fingerprint() == ""

    def test_parameters_that_cannot_be_honored_stay_out_of_the_fingerprint(self):
        """A dropped parameter did not change the answer, so it must not split the cache."""
        assert SamplingParams(n=4).cache_fingerprint() == ""
        assert SamplingParams(logprobs=True).cache_fingerprint() == ""


class TestParsingFromClientBody:
    def test_response_format_object_is_recognized(self):
        params = SamplingParams.from_openai_body(
            {"response_format": {"type": "json_object"}}
        )
        assert params.response_format_json is True

    def test_other_response_formats_are_not_treated_as_json(self):
        params = SamplingParams.from_openai_body({"response_format": {"type": "text"}})
        assert params.response_format_json is False

    def test_string_stop_is_normalized_to_a_list(self):
        assert SamplingParams.from_openai_body({"stop": "END"}).stop == ["END"]

    def test_tool_choice_string_is_kept(self):
        assert SamplingParams.from_openai_body({"tool_choice": "none"}).tool_choice == "none"

    def test_tool_choice_object_reads_as_required(self):
        """`{"type": "function", ...}` names a specific function to force."""
        body = {"tool_choice": {"type": "function", "function": {"name": "f"}}}
        assert SamplingParams.from_openai_body(body).tool_choice == "required"

    def test_unknown_keys_are_ignored_without_error(self):
        assert SamplingParams.from_openai_body({"future_param": 1}) == SamplingParams()

    @pytest.mark.parametrize("value", [0, -5, None])
    def test_non_positive_max_tokens_is_dropped(self, value):
        assert SamplingParams.from_openai_body({"max_tokens": value}).max_tokens is None

    def test_max_completion_tokens_is_accepted_as_an_alias(self):
        """Newer OpenAI clients send max_completion_tokens instead."""
        params = SamplingParams.from_openai_body({"max_completion_tokens": 32})
        assert params.max_tokens == 32

    def test_max_tokens_wins_when_the_newer_key_is_present_but_null(self):
        """A parsed request body carries both keys, one of them None."""
        body = {"max_tokens": 24, "max_completion_tokens": None}
        assert SamplingParams.from_openai_body(body).max_tokens == 24

    def test_newer_key_takes_precedence_when_both_are_set(self):
        body = {"max_tokens": 24, "max_completion_tokens": 99}
        assert SamplingParams.from_openai_body(body).max_tokens == 99


class TestAnthropicBody:
    def test_anthropic_names_are_read(self):
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 100, "top_p": 0.5, "top_k": 10, "stop_sequences": ["END"]}
        )
        assert params.max_tokens == 100
        assert params.top_p == 0.5
        assert params.top_k == 10
        assert params.stop == ["END"]

    def test_top_k_maps_to_ollama_but_not_to_openai(self):
        """top_k is not in the chat-completions schema; strict providers 400 on it."""
        params = SamplingParams(top_k=7)
        assert params.ollama_options()["top_k"] == 7
        assert "top_k" not in params.openai_payload()

    def test_responses_cap_is_read_from_its_own_key(self):
        params = SamplingParams.from_responses_body(
            {"max_output_tokens": 15, "top_p": 0.9, "max_tokens": None}
        )
        assert params.max_tokens == 15
        assert params.top_p == 0.9

    def test_ollama_option_names_are_read(self):
        params = SamplingParams.from_ollama_options(
            {"num_predict": 30, "top_k": 4, "seed": 2, "stop": ["END"], "temperature": 0.1}
        )
        assert params.max_tokens == 30
        assert params.top_k == 4
        assert params.seed == 2
        assert params.stop == ["END"]

    def test_ollama_unlimited_sentinel_is_not_a_request(self):
        """-1 means 'no limit', which is the same as asking for nothing."""
        assert SamplingParams.from_ollama_options({"num_predict": -1}).max_tokens is None

    def test_top_k_splits_the_cache(self):
        assert SamplingParams(top_k=7).cache_fingerprint() != SamplingParams().cache_fingerprint()
