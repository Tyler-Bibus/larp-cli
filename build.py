#!/usr/bin/env python3
"""Build a standalone Python zipapp; no packages or network access needed."""

from pathlib import Path
import shutil
import tempfile
import zipapp


def main():
    root = Path(__file__).resolve().parent
    output = root / "dist/lrp"
    output.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lrp-build-") as directory:
        source = Path(directory)
        shutil.copytree(root / "lrp", source / "lrp", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (source / "__main__.py").write_text("from lrp.app import main\nraise SystemExit(main())\n")
        zipapp.create_archive(source, output, interpreter="/usr/bin/env python3",
                              compressed=True)
    output.chmod(0o755)
    print(f"Built {output}. Run it directly or keep using the checkout's lrp launcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
