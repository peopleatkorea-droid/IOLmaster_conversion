import unittest

import numpy as np

from modeling.analyze_pediatric_longitudinal_growth import (
    continuous_geometry_associations,
    fit_ols,
    nested_comparison,
    solve_ols,
    threshold_24_summary,
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

    def test_continuous_geometry_associations_preserve_expected_directions(self):
        rng = np.random.default_rng(20260715)
        records = []
        for index, age in enumerate(np.linspace(8.5, 11.5, 160)):
            female = float(index % 2)
            latent = rng.normal()
            records.append(
                {
                    "age": age,
                    "follow_age": age + 2.0,
                    "female": female,
                    "AL_baseline": 23.5 + 0.2 * age + 0.1 * female + latent,
                    "K_baseline": 44.0 - 0.6 * latent + rng.normal(scale=0.1),
                    "ACD_baseline": 3.4 + 0.2 * latent + rng.normal(scale=0.04),
                    "AL_follow": 24.0 + 0.2 * age + 0.1 * female + latent,
                    "K_follow": 43.9 - 0.5 * latent + rng.normal(scale=0.1),
                    "ACD_follow": 3.5 + 0.2 * latent + rng.normal(scale=0.04),
                }
            )
        associations = continuous_geometry_associations(records)
        self.assertLess(associations["baseline"]["K"]["rho"], -0.8)
        self.assertGreater(associations["baseline"]["ACD"]["rho"], 0.8)
        self.assertLess(associations["follow"]["K"]["rho"], -0.8)
        self.assertGreater(associations["follow"]["ACD"]["rho"], 0.8)

    def test_threshold_24_summary_counts_boundary_as_exposed(self):
        records = [
            {"AL_baseline": 23.0},
            {"AL_baseline": 24.0},
            {"AL_baseline": 24.5},
        ]
        summary = threshold_24_summary(records)
        self.assertEqual(summary["n_at_or_above_24"], 2)
        self.assertAlmostEqual(summary["percent_at_or_above_24"], 200.0 / 3.0)
        self.assertEqual(summary["n_between_23_5_and_24_5"], 2)


if __name__ == "__main__":
    unittest.main()
