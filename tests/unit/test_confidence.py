from __future__ import annotations

from daari.router.confidence import score_l3_confidence


class TestScoreL3Confidence:
    def test_short_response_fails(self):
        assert score_l3_confidence("ok") == 0.0
        assert score_l3_confidence("          ") == 0.0

    def test_refusal_phrases_fail(self):
        assert score_l3_confidence("I cannot help with that request today.") == 0.0
        assert score_l3_confidence("As an AI, I don't have access to your files.") == 0.0

    def test_good_response_passes(self):
        content = "Here is a detailed answer to your question about routing."
        assert score_l3_confidence(content) == 1.0
