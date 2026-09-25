#!/usr/bin/env python3
"""Install a user-local launcher without packages, root, or shell startup hooks."""
import argparse
import os
from pathlib import Path
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(description="Install LRP for the current user.")
    parser.add_argument("--uninstall", action="store_true", help="remove this checkout's launcher; preserve notes")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent / "bin/lrp"
    target = Path.home() / ".local/bin/lrp"
    if args.uninstall:
        if target.is_symlink() and target.resolve() == source:
            target.unlink()
            print("Removed the lrp launcher. Source and saved notes are preserved.")
            return 0
        print("No launcher belonging to this checkout was found.")
        return 0
    if os.path.lexists(target) and not (target.is_symlink() and target.resolve() == source):
        print(f"Refusing to replace existing command: {target}", file=sys.stderr)
        return 1
    other = shutil.which("lrp")
    if other and Path(other).resolve() != source:
        print(f"Command lrp is already used by {other}; existing command preserved.", file=sys.stderr)
        return 1
    source.chmod(source.stat().st_mode | 0o111)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_symlink():
        target.symlink_to(source)
    print(f"Installed {target} -> {source}\nStart in Konsole: lrp")
    if str(target.parent) not in os.environ.get("PATH", "").split(os.pathsep):
        print('If needed, add this to ~/.bashrc: export PATH="$HOME/.local/bin:$PATH"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
