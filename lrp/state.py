"""Small, bounded, atomic local store. Never overwrite unreadable user data."""

import json
import os
from pathlib import Path
import tempfile
import unicodedata


def clean(text):
    return "".join(c for c in str(text) if not unicodedata.category(c).startswith("C"))


def state_path():
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return base / "lrp" / "state.json"


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else state_path()
        self.error = ""
        self.blocked = False
        self.data = {"callsign": "OPERATOR", "aura": 670, "sessions": 0, "notes": [], "calm": False}
        try:
            if self.path.exists():
                if self.path.stat().st_size > 2_000_000:
                    raise ValueError("state file exceeds 2 MB")
                raw = json.loads(self.path.read_text())
                if not isinstance(raw, dict):
                    raise ValueError("state must be an object")
                for key in ("aura", "sessions"):
                    if type(raw.get(key, self.data[key])) is not int:
                        raise ValueError(f"invalid {key}")
                    self.data[key] = max(-999999, min(999999, raw.get(key, self.data[key])))
                self.data["callsign"] = clean(raw.get("callsign", "OPERATOR"))[:24] or "OPERATOR"
                self.data["calm"] = raw.get("calm") is True
                notes = raw.get("notes", [])
                if not isinstance(notes, list) or any(not isinstance(n, dict) for n in notes):
                    raise ValueError("invalid notes")
                self.data["notes"] = [{"time": clean(n.get("time", ""))[:32],
                                       "text": clean(n.get("text", ""))[:1000]} for n in notes[-200:]]
        except (OSError, ValueError, TypeError) as exc:
            self.error = f"Read-only session: {exc}. Original state preserved."
            self.blocked = True

    def save(self):
        if self.blocked:
            return False
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, prefix=".state-",
                                             delete=False) as stream:
                temporary = stream.name
                json.dump(self.data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.error = ""
            return True
        except OSError as exc:
            self.error = f"Could not save: {exc}"
            return False
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
