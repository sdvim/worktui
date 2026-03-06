import json
import os
from pathlib import Path

LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
GITHUB_REPO = os.environ.get("WORKTUI_GITHUB_REPO", "courtyard-nft/courtyard-frontend")
GITHUB_ORG = os.environ.get("WORKTUI_GITHUB_ORG", "courtyard-nft")
GITHUB_USER = os.environ.get("WORKTUI_GITHUB_USER", "sdvim")
POLL_INTERVAL = int(os.environ.get("WORKTUI_POLL_INTERVAL", "45"))

SETTINGS_PATH = Path.home() / ".config" / "worktui" / "settings.json"

_DEFAULTS = {
    "enable_linear": True,
    "enable_github_issues": False,
}


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text())
            return {**_DEFAULTS, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULTS)


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2))


def load_starred() -> set[str]:
    settings = load_settings()
    return set(settings.get("starred", []))


def toggle_starred(item_id: str) -> bool:
    """Toggle star for item_id. Returns True if now starred."""
    settings = load_settings()
    starred = set(settings.get("starred", []))
    if item_id in starred:
        starred.discard(item_id)
        is_starred = False
    else:
        starred.add(item_id)
        is_starred = True
    settings["starred"] = sorted(starred)
    save_settings(settings)
    return is_starred
