"""Verdier du legger inn selv i dashbordet, lagret lokalt i innstillinger.json.

Brukes for tall Garmin viser i appen, men som ikke er tilgjengelige via API-et
(f.eks. CSS — kritisk svømmehastighet).
"""

import json
import re
from pathlib import Path

_SETTINGS_FILE = Path(__file__).parent / "innstillinger.json"
_PACE_PATTERN = re.compile(r"^\s*(\d{1,2}):([0-5]\d)\s*$")


def load_settings() -> dict:
    try:
        return json.loads(_SETTINGS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_setting(key: str, value) -> None:
    settings = load_settings()
    settings[key] = value
    _SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False))


def parse_pace(text: str) -> int | None:
    """'1:45' → 105 sekunder. None hvis formatet ikke er m:ss."""
    match = _PACE_PATTERN.match(text or "")
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))
