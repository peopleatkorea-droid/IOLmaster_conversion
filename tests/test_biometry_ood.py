import unittest

from biometry_ood import age_at_measurement, load_default_model, mean_k_from_radii


class BiometryOODTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = load_default_model()

    def test_model_provenance_and_size(self):
        self.assertEqual(self.model.version, "continuous-age-bilateral-v3.1.0")
        self.assertEqual(len(self.model.models), 2)
        counts = {model.payload["model_key"]: len(model.reference_distances) for model in self.model.models}
        self.assertEqual(
            counts,
            {
                "bilateral_core": 1246,
                "bilateral_extended": 1245,
            },
        )
        for model in self.model.models:
            self.assertEqual(model.reference_distances, sorted(model.reference_distances))
            self.assertEqual(model.payload["reference_patients"], 681)
            self.assertGreater(model.payload["reference_rows"], model.payload["reference_patients"])

    def test_mean_k_from_equal_radii(self):
        radius = 337.5 / 40.8
        self.assertAlmostEqual(mean_k_from_radii(radius, radius), 40.8, places=10)

    def test_age_calculation(self):
        age = age_at_measurement("1940-01-01", "2020-01-01")
        self.assertAlmostEqual(age, 80.0, delta=0.01)

    def test_user_example_is_uncommon(self):
        result = self.model.score_values(80, 23.61, 40.80, 1.94, 5.58)
        self.assertEqual(result["OOD_Status"], "Uncommon anatomy")
        self.assertAlmostEqual(result["OOD_Percentile"], 92.212, places=3)
        self.assertIn("ACD -", result["OOD_Dominant_Deviation"])
        self.assertEqual(result["OOD_Age_Stratum"], "Continuous age-adjusted bilateral")
        self.assertEqual(result["OOD_Model_Tier"], "Core")
        self.assertEqual(
            result["OOD_Reference_Context"],
            "About 1 in 10-15 age-weighted calibration eyes is this unusual or more",
        )
        self.assertGreater(result["OOD_Local_Calibration_Effective_N"], 350)
        self.assertGreater(result["OOD_Local_Calibration_Max_Percentile"], 99)
        self.assertIsNone(result["OOD_Calibration_Warning"])
        self.assertIsNone(result["OOD_Model_Selection_Warning"])
        self.assertEqual(len(result["OOD_Feature_Profile"]), 4)

    def test_wtw_cct_select_extended_model(self):
        result = self.model.score_values(80, 23.61, 40.80, 1.94, 5.58, 10.99, 0.601)
        self.assertEqual(result["OOD_Model_Tier"], "Extended")
        self.assertEqual(result["OOD_Model_Version"], "bilateral-extended-v3.1.0")
        self.assertAlmostEqual(result["OOD_Percentile"], 95.725, places=3)
        self.assertEqual(
            result["OOD_Reference_Context"],
            "About 1 in 20-30 age-weighted calibration eyes is this unusual or more",
        )
        self.assertAlmostEqual(result["OOD_Core_Sensitivity_Percentile"], 92.212, places=3)
        self.assertEqual(result["OOD_Core_Sensitivity_Status"], "Uncommon anatomy")

    def test_invalid_optional_input_warns_before_core_fallback(self):
        result = self.model.score_values(80, 23.61, 40.80, 1.94, 5.58, 7.5, 0.601)
        self.assertEqual(result["OOD_Model_Tier"], "Core")
        self.assertIn("WTW is outside 8-16", result["OOD_Model_Selection_Warning"])
        self.assertIn("Valid CCT input was ignored", result["OOD_Model_Selection_Warning"])

    def test_sparse_age_local_calibration_warns_about_ceiling(self):
        result = self.model.score_values(25, 25.68, 43.30, 3.68, 3.52, 12.0, 0.54)
        self.assertEqual(result["OOD_Model_Tier"], "Extended")
        self.assertLess(result["OOD_Local_Calibration_Max_Percentile"], 97.5)
        self.assertLess(result["OOD_Local_Calibration_Effective_N"], 50)
        self.assertIn("Rare threshold is not attainable", result["OOD_Calibration_Warning"])

    def test_age_is_continuous_across_former_boundaries(self):
        values = (23.05, 43.31, 3.55, 3.47)
        before_18 = self.model.score_values(17.99, *values)
        after_18 = self.model.score_values(18.0, *values)
        self.assertLess(abs(before_18["OOD_Percentile"] - after_18["OOD_Percentile"]), 1.0)
        values_40 = (24.0, 43.6, 3.3, 4.2)
        before_40 = self.model.score_values(39.99, *values_40)
        after_40 = self.model.score_values(40.0, *values_40)
        self.assertLess(abs(before_40["OOD_Percentile"] - after_40["OOD_Percentile"]), 0.1)
        self.assertEqual(self.model.select_model(8).payload["model_key"], "bilateral_core")
        self.assertEqual(self.model.select_model(80).payload["model_key"], "bilateral_core")

    def test_age_local_percentile_never_reaches_100(self):
        result = self.model.score_values(25, 38, 65, 0.8, 8)
        self.assertLess(result["OOD_Percentile"], 100)

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
