import argparse
import shutil
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_FILES = (
    ("web/index.html", "web/index.html"),
    ("web/styles.css", "web/styles.css"),
    ("web/app.js", "web/app.js"),
    ("web/ood-core.js", "web/ood-core.js"),
    ("web/demo-examples.js", "web/demo-examples.js"),
    ("models/biometry_ood_bilateral_v32.json", "models/biometry_ood_bilateral_v32.json"),
)
ROOT_INDEX = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="0; url=web/">
  <title>Biometry OOD Explorer</title>
</head>
<body>
  <p><a href="web/">Open Biometry OOD Explorer</a></p>
</body>
</html>
"""


def build_static_site(output_directory):
    output_directory = Path(output_directory).resolve()
    expected_files = {Path("index.html")}
    expected_files.update(Path(destination) for _, destination in ALLOWED_FILES)

    if output_directory.exists():
        existing_files = {
            path.relative_to(output_directory)
            for path in output_directory.rglob("*")
            if path.is_file()
        }
        unexpected = sorted(existing_files - expected_files)
        if unexpected:
            names = ", ".join(str(path) for path in unexpected)
            raise RuntimeError(
                f"Refusing to build into a directory containing non-allowlisted files: {names}"
            )

    output_directory.mkdir(parents=True, exist_ok=True)
    with (output_directory / "index.html").open(
        "w", encoding="utf-8", newline="\n"
    ) as root_index:
        root_index.write(ROOT_INDEX)

    for source_name, destination_name in ALLOWED_FILES:
        source = REPOSITORY_ROOT / source_name
        if not source.is_file():
            raise FileNotFoundError(f"Required deployment file is missing: {source}")
        destination = output_directory / destination_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    actual_files = {
        path.relative_to(output_directory)
        for path in output_directory.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise RuntimeError("Static deployment output does not match the allowlist.")
    return sorted(actual_files)


def main():
    parser = argparse.ArgumentParser(
        description="Build an allowlisted static deployment for the Biometry OOD Explorer."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "dist" / "web-static",
        help="Output directory (default: dist/web-static)",
    )
    args = parser.parse_args()
    files = build_static_site(args.output)
    print(f"Built {len(files)} allowlisted static files in {args.output.resolve()}")
    for path in files:
        print(f"  {path.as_posix()}")


if __name__ == "__main__":
    main()
