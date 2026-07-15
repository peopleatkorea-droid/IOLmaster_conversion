import unittest

import numpy as np

from modeling.analyze_pediatric_longitudinal_growth import (
    fit_ols,
    nested_comparison,
    solve_ols,
    winsorize,
)


class PediatricLongitudinalGrowthTests(unittest.TestCase):
    def test_ols_recovers_known_coefficients(self):
        x = np.linspace(-2.0, 2.0, 101)
        y = 1.5 + 0.25 * x
        fit = fit_ols(x[:, None], y, ["x"])
        self.assertAlmostEqual(fit["coefficients"]["intercept"]["estimate"], 1.5, places=12)
        self.assertAlmostEqual(fit["coefficients"]["x"]["estimate"], 0.25, places=12)
        self.assertAlmostEqual(fit["r2"], 1.0, places=12)

    def test_residualized_predictor_spans_same_model_space(self):
        rng = np.random.default_rng(20260714)
        age = np.linspace(8.5, 12.5, 200)
        sex = np.tile([0.0, 1.0], 100)
        al = 21.0 + 0.3 * age + 0.2 * sex + rng.normal(0.0, 0.4, len(age))
        outcome = -0.2 + 0.03 * age + 0.04 * al + rng.normal(0.0, 0.05, len(age))
        expected_x = np.column_stack([age, age**2, sex])
        expected_beta, expected = solve_ols(expected_x, al)
        residual = al - expected

        raw_fit = fit_ols(np.column_stack([expected_x, al]), outcome, ["age", "age2", "sex", "al"])
        residual_fit = fit_ols(
            np.column_stack([expected_x, residual]),
            outcome,
            ["age", "age2", "sex", "al_residual"],
        )
        np.testing.assert_allclose(raw_fit["_fitted"], residual_fit["_fitted"], atol=1e-12)
        self.assertEqual(expected_beta.shape[0], 4)

    def test_nested_comparison_detects_added_signal(self):
        rng = np.random.default_rng(42)
        x = rng.normal(size=300)
        z = rng.normal(size=300)
        y = 0.7 * x + 1.2 * z + rng.normal(scale=0.2, size=300)
        reduced = fit_ols(x[:, None], y, ["x"])
        full = fit_ols(np.column_stack([x, z]), y, ["x", "z"])
        comparison = nested_comparison(reduced, full)
        self.assertLess(comparison["p_value"], 1e-20)
        self.assertGreater(comparison["partial_r2"], 0.8)

    def test_winsorize_uses_requested_limits(self):
        values = np.arange(101, dtype=float)
        clipped, limits = winsorize(values, 0.01, 0.99)
        self.assertEqual(clipped.min(), 1.0)
        self.assertEqual(clipped.max(), 99.0)
        self.assertEqual(limits["lower_value"], 1.0)
        self.assertEqual(limits["upper_value"], 99.0)


if __name__ == "__main__":
    unittest.main()
