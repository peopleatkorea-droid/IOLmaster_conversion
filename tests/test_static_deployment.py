import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPOSITORY_ROOT / "deployment" / "build_static_site.py"
EXPECTED_FILES = {
    "index.html",
    "models/biometry_ood_bilateral_v32.json",
    "web/app.js",
    "web/demo-examples.js",
    "web/index.html",
    "web/ood-core.js",
    "web/styles.css",
}


class StaticDeploymentTests(unittest.TestCase):
    def test_build_contains_only_allowlisted_static_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "site"
            subprocess.run(
                [sys.executable, str(BUILD_SCRIPT), "--output", str(output)],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            actual = {
                path.relative_to(output).as_posix()
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual, EXPECTED_FILES)

            html = (output / "web" / "index.html").read_text(encoding="utf-8")
            self.assertIn("All calculations run in this browser", html)
            self.assertIn("Research and education use only", html)
            self.assertIn("Internal untouched test cohort", html)
            self.assertNotIn("<form action=", html)

    def test_build_refuses_unexpected_output_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "site"
            output.mkdir()
            (output / "source.xlsx").write_text("not clinical data", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(BUILD_SCRIPT), "--output", str(output)],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("non-allowlisted files", completed.stderr)


if __name__ == "__main__":
    unittest.main()
