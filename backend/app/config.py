"""Application environment loading anchored to the backend project."""

from pathlib import Path
import os
from typing import Optional

from dotenv import dotenv_values, load_dotenv


def backend_env_path() -> Path:
    """Return backend/.env regardless of the process working directory."""
    return Path(__file__).resolve().parents[1] / ".env"


def load_environment(env_path: Optional[Path] = None) -> bool:
    """Load backend environment, preserving non-empty process settings."""
    resolved_path = env_path or backend_env_path()
    loaded = load_dotenv(dotenv_path=resolved_path, override=False)
    # A process manager can export these names with empty values. python-dotenv
    # treats them as already set with override=False, so fill only unset/blank
    # entries from the backend file while retaining any actual process value.
    for name, value in dotenv_values(resolved_path).items():
        if value is not None and not os.environ.get(name):
            os.environ[name] = value
            loaded = True
    return loaded
