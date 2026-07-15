import unittest

import numpy as np

from modeling.analyze_pediatric_al_phenotypes import (
    RestrictedCubicSpline,
    benjamini_hochberg,
    deterministic_eye_index,
)


class PediatricALPhenotypeTests(unittest.TestCase):
    def test_eye_selection_is_deterministic(self):
        first = deterministic_eye_index("patient-123", 2, 20260714)
        second = deterministic_eye_index("patient-123", 2, 20260714)
        self.assertEqual(first, second)
        self.assertIn(first, {0, 1})

    def test_restricted_cubic_spline_has_linear_tails(self):
        spline = RestrictedCubicSpline().fit(np.linspace(3, 17, 100))
        transformed = spline.transform([18, 19, 20])
        second_difference = transformed[2] - 2 * transformed[1] + transformed[0]
        np.testing.assert_allclose(second_difference, 0.0, atol=1e-12)

    def test_benjamini_hochberg_adjustment(self):
        adjusted = benjamini_hochberg(np.asarray([0.01, 0.10, 0.20]))
        np.testing.assert_allclose(adjusted, [0.03, 0.15, 0.20])


if __name__ == "__main__":
    unittest.main()
