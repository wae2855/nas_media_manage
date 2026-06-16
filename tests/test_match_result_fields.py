import unittest
from media_importer.features.scraping.match_models import MatchResult, SelectedCandidate
from media_importer.features.scraping.match_enums import TierShortReason, WhySelected


class TestMatchResultFields(unittest.TestCase):
    def test_to_dict_includes_new_fields(self):
        r = MatchResult(
            match_level="AUTO_PASS",
            match_tier=1,
            tier_short_reason=TierShortReason.TIER1_UNIQUE,
            ai_reason="AI推理",
            selected_candidate=SelectedCandidate(
                provider_type="tmdb", provider_id="637",
                title="美丽人生", year=1997, media_type="movie",
                why_selected=WhySelected.UNIQUE_MATCH, score=8.5,
            ),
        )
        d = r.to_dict()
        self.assertEqual(d["tier_short_reason"], "唯一精确匹配")
        self.assertEqual(d["ai_reason"], "AI推理")
        self.assertEqual(d["selected_candidate"]["why_selected"], "unique_match")
        self.assertNotIn("confirm_reason", d)

    def test_confirm_reason_not_in_output(self):
        r = MatchResult(match_level="NEEDS_CONFIRM")
        d = r.to_dict()
        self.assertNotIn("confirm_reason", d)

    def test_selected_candidate_none(self):
        r = MatchResult(match_level="FAILED")
        d = r.to_dict()
        self.assertIsNone(d["selected_candidate"])


if __name__ == "__main__":
    unittest.main()
