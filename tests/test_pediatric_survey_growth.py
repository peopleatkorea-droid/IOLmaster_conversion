import unittest

from modeling.analyze_pediatric_survey_growth import (
    ACTIVITY_CODE_LABELS,
    bh_adjust,
    cohen_kappa,
)


class PediatricSurveyGrowthTests(unittest.TestCase):
    def test_bh_adjust_is_monotone_in_ranked_order(self):
        values = [0.04, 0.001, 0.02, 0.8]
        adjusted = bh_adjust(values)
        ranked = sorted(zip(values, adjusted), key=lambda pair: pair[0])
        self.assertTrue(all(first[1] <= second[1] for first, second in zip(ranked, ranked[1:])))
        self.assertTrue(all(raw <= corrected <= 1.0 for raw, corrected in zip(values, adjusted)))

    def test_cohen_kappa_perfect_agreement(self):
        self.assertEqual(cohen_kappa([1, 2, 1, 2], [1, 2, 1, 2]), 1.0)

    def test_activity_labels_are_mutually_exclusive_source_intervals(self):
        self.assertEqual(
            list(ACTIVITY_CODE_LABELS.values()),
            [
                "<=1 hour/day",
                ">1 to 2 hours/day",
                ">2 to 3 hours/day",
                ">3 to 4 hours/day",
                ">4 hours/day",
            ],
        )


if __name__ == "__main__":
    unittest.main()
