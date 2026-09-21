"""Environment-backed configuration. Secrets stay out of the repo."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _parse_chat_ids(raw: str | None) -> frozenset[int]:
    text = (raw or "").strip()
    if not text:
        return frozenset()
    out: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        out.add(int(part))
    return frozenset(out)


def _parse_bool(raw: str | None, *, default: bool = False) -> bool:
    """Parse the small, explicit boolean vocabulary used by environment flags."""
    text = (raw or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def _default_data_dir() -> Path:
    override = (os.getenv("MCP_TELEGRAM_DATA_DIR") or "").strip()
    if override:
        return Path(override).expanduser()
    base = Path(os.getenv("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    return base / "mcp-telegram-bridge"


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from the environment."""

    bot_token: str
    allowed_chat_ids: frozenset[int] = field(default_factory=frozenset)
    data_dir: Path = field(default_factory=_default_data_dir)
    api_base: str = "https://api.telegram.org"
    safety_strict: bool = False

    @property
    def has_chat_filter(self) -> bool:
        return bool(self.allowed_chat_ids)

    def chat_allowed(self, chat_id: int) -> bool:
        if not self.allowed_chat_ids:
            return True
        return int(chat_id) in self.allowed_chat_ids

    @classmethod
    def from_env(cls, *, require_token: bool = True) -> Settings:
        token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        if require_token and not token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env "
                "or export the token before starting the MCP server."
            )
        return cls(
            bot_token=token,
            allowed_chat_ids=_parse_chat_ids(os.getenv("ALLOWED_CHAT_IDS")),
            safety_strict=_parse_bool(os.getenv("SAFETY_STRICT")),
            data_dir=_default_data_dir(),
        )


def load_dotenv_if_present(path: Path | None = None) -> None:
    """Best-effort load of a local .env without adding a hard dependency."""
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path)
    else:
        candidates.append(Path.cwd() / ".env")
        # When installed editable, also check project root above src/
        here = Path(__file__).resolve()
        candidates.append(here.parents[2] / ".env")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            continue
        break
