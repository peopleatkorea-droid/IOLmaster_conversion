import unittest

from biometry_ood import age_at_measurement, load_default_model, mean_k_from_radii


class BiometryOODTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = load_default_model()

    def test_model_provenance_and_size(self):
        self.assertEqual(self.model.version, "age-stratified-v2.0.0")
        self.assertEqual(len(self.model.models), 6)
        counts = {model.payload["model_key"]: len(model.reference_distances) for model in self.model.models}
        self.assertEqual(
            counts,
            {
                "pediatric_core": 976,
                "pediatric_extended": 967,
                "young_adult_core": 317,
                "young_adult_extended": 315,
                "adult_core": 6876,
                "adult_extended": 6874,
            },
        )
        for model in self.model.models:
            self.assertEqual(model.reference_distances, sorted(model.reference_distances))

    def test_mean_k_from_equal_radii(self):
        radius = 337.5 / 40.8
        self.assertAlmostEqual(mean_k_from_radii(radius, radius), 40.8, places=10)

    def test_age_calculation(self):
        age = age_at_measurement("1940-01-01", "2020-01-01")
        self.assertAlmostEqual(age, 80.0, delta=0.01)

    def test_user_example_is_uncommon(self):
        result = self.model.score_values(80, 23.61, 40.80, 1.94, 5.58)
        self.assertEqual(result["Anatomy_Score"], 1)
        self.assertEqual(result["OOD_Status"], "Uncommon anatomy")
        self.assertAlmostEqual(result["OOD_Percentile"], 93.572, places=3)
        self.assertIn("ACD vs age", result["OOD_Dominant_Deviation"])
        self.assertEqual(result["OOD_Age_Stratum"], "Adult cataract-age")
        self.assertEqual(result["OOD_Model_Tier"], "Core")

    def test_wtw_cct_select_extended_model(self):
        result = self.model.score_values(80, 23.61, 40.80, 1.94, 5.58, 10.99, 0.601)
        self.assertEqual(result["OOD_Model_Tier"], "Extended")
        self.assertEqual(result["OOD_Model_Version"], "adult-extended-v2.0.0")
        self.assertAlmostEqual(result["OOD_Percentile"], 96.392, places=3)

    def test_age_selects_stratum(self):
        pediatric = self.model.score_values(8, 23.05, 43.31, 3.55, 3.47)
        young = self.model.score_values(25, 25.68, 43.30, 3.68, 3.52)
        adult = self.model.score_values(40, 24.0, 43.6, 3.3, 4.2)
        self.assertEqual(pediatric["OOD_Age_Stratum"], "Pediatric")
        self.assertEqual(young["OOD_Age_Stratum"], "Young adult")
        self.assertEqual(adult["OOD_Age_Stratum"], "Adult cataract-age")
        self.assertEqual(self.model.select_model(17.999).stratum_label, "Pediatric")
        self.assertEqual(self.model.select_model(18.0).stratum_label, "Young adult")
        self.assertEqual(self.model.select_model(40.0).stratum_label, "Adult cataract-age")

    def test_missing_date_retains_calculated_mean_k(self):
        result = self.model.score_row(
            {"DOB": None, "Acquisition_Date": None, "R1": 8.0, "R2": 8.0}
        )
        self.assertEqual(result["OOD_Status"], "Not calculated")
        self.assertAlmostEqual(result["Mean_K"], 42.1875, places=4)

    def test_age_outside_validated_range_is_not_calculated(self):
        result = self.model.score_values(1.5, 23.5, 44.0, 3.0, 4.0)
        self.assertEqual(result["OOD_Status"], "Not calculated")
        self.assertIsNone(result["OOD_Distance"])

    def test_precision_matrix_reconstructs_identity(self):
        for model in self.model.models:
            covariance = model.payload["robust_covariance"]
            precision = model.payload["precision_matrix"]
            size = len(covariance)
            for i in range(size):
                for j in range(size):
                    value = sum(covariance[i][k] * precision[k][j] for k in range(size))
                    self.assertAlmostEqual(value, 1.0 if i == j else 0.0, places=8)


if __name__ == "__main__":
    unittest.main()
