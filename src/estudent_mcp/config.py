"""Runtime configuration loaded from environment / .env file.

Credentials live only on the local machine. Nothing here is committed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root = three levels up from this file (src/estudent_mcp/config.py).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
STORAGE_STATE_PATH = RUNTIME_DIR / "storage_state.json"
SCREENSHOT_DIR = RUNTIME_DIR / "screenshots"


@dataclass(frozen=True)
class Config:
    netid: str
    password: str
    base_url: str
    headful: bool

    @property
    def has_credentials(self) -> bool:
        return bool(self.netid and self.password)


def load_config() -> Config:
    """Load configuration from .env / environment.

    Does not raise if credentials are missing — callers that need them should
    check `Config.has_credentials` and surface a friendly error. This lets
    read-only introspection (e.g. tool listing) work without a configured .env.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    RUNTIME_DIR.mkdir(exist_ok=True)
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    return Config(
        netid=os.getenv("ESTUDENT_NETID", "").strip(),
        password=os.getenv("ESTUDENT_PASSWORD", "").strip(),
        base_url=os.getenv(
            "ESTUDENT_BASE_URL", "https://www.polyu.edu.hk/student"
        ).strip(),
        headful=os.getenv("ESTUDENT_HEADFUL", "0").strip() in ("1", "true", "True"),
    )
