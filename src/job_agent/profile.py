from pathlib import Path

import yaml


def load_profile(path: str | Path = "profile.yaml") -> dict:
    """Load the user's profile (the single source of truth about their experience)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Copy profile.example.yaml to profile.yaml and fill it in."
        )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def profile_to_text(profile: dict) -> str:
    return yaml.safe_dump(profile, allow_unicode=True, sort_keys=False)
