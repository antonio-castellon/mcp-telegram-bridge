"""Environment-backed configuration. Secrets stay out of the repo."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Sensible defaults for a single-tenant, agent-driven bridge. They blunt
# runaway loops and floods. They are not a public-bot moderation policy.
DEFAULT_MAX_INBOUND_CHARS = 4096
DEFAULT_MAX_UPDATE_BYTES = 65_536
MAX_INBOUND_CHARS_CEILING = 32_768
MAX_UPDATE_BYTES_CEILING = 262_144
DEFAULT_INBOUND_CHAT_RATE = (60, 60.0)
DEFAULT_INBOUND_GLOBAL_RATE = (120, 60.0)
DEFAULT_INBOUND_POLL_RATE = (30, 60.0)
DEFAULT_OUTBOUND_CHAT_RATE = (20, 60.0)
DEFAULT_OUTBOUND_GLOBAL_RATE = (60, 60.0)

_RATE_OFF = {"off", "0", "none", "disabled", "false", "no"}


def _parse_chat_ids(raw: str | None) -> frozenset[int]:
    text = (raw or "").strip()
    if not text:
        return frozenset()
    out: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError as exc:
            raise RuntimeError(
                "ALLOWED_CHAT_IDS must be a comma-separated list of integers"
            ) from exc
    return frozenset(out)


def startup_warnings(settings: Settings) -> list[str]:
    """Operator warnings for the access mode. Never includes the bot token."""
    if settings.allowed_chat_ids and settings.allow_all_chats:
        return [
            "ALLOW_ALL_CHATS is set but ALLOWED_CHAT_IDS is non-empty; "
            "the allowlist is enforced and open mode is not used."
        ]
    if settings.open_mode:
        return [
            "ALLOW_ALL_CHATS is enabled and no chat allowlist is set. "
            "Every chat is permitted. Disable open mode unless you intend that."
        ]
    if not settings.allowed_chat_ids:
        return [
            "ALLOWED_CHAT_IDS is empty and ALLOW_ALL_CHATS is off. "
            "All chats are denied until you set an allowlist or explicitly enable open mode."
        ]
    return []


def emit_startup_warnings(settings: Settings, stream=None) -> None:
    """Write access-mode warnings to stderr. Stdout is the MCP protocol."""
    import sys

    out = stream if stream is not None else sys.stderr
    for line in startup_warnings(settings):
        print(f"mcp-telegram-bridge: {line}", file=out, flush=True)


def _parse_bool(raw: str | None, *, default: bool = False) -> bool:
    """Parse the small, explicit boolean vocabulary used by environment flags."""
    text = (raw or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def _parse_bounded_int(
    raw: str | None,
    *,
    name: str,
    default: int,
    ceiling: int,
) -> int:
    text = (raw or "").strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 1 or value > ceiling:
        raise RuntimeError(f"{name} must be between 1 and {ceiling}")
    return value


def _parse_rate(
    raw: str | None,
    *,
    name: str,
    default: tuple[int, float] | None,
) -> tuple[int, float] | None:
    """Parse ``count/seconds``. ``off`` disables the limit."""
    if raw is None:
        return default
    text = raw.strip().lower()
    if not text:
        return default
    if text in _RATE_OFF:
        return None
    count_text, sep, window_text = text.partition("/")
    if not sep:
        window_text = "60"
    try:
        count = int(count_text.strip())
        window = float(window_text.strip())
    except ValueError as exc:
        raise RuntimeError(
            f"{name} must look like 20/60 (count/seconds) or off"
        ) from exc
    if count < 0 or window <= 0:
        raise RuntimeError(f"{name} must look like 20/60 (count/seconds) or off")
    if count == 0:
        return None
    return (count, window)


def _default_data_dir() -> Path:
    """Resolve button-map / claim state directory.

    Preference order:
    1. ``MCP_TELEGRAM_BRIDGE_DATA_DIR`` (documented)
    2. ``MCP_TELEGRAM_DATA_DIR`` (legacy alias)
    3. platformdirs user_data_dir when available
    4. ``$XDG_DATA_HOME/mcp-telegram-bridge`` or ``~/.local/share/...``
       (cache fallback: ``$XDG_CACHE_HOME`` / ``~/.cache``)
    """
    for key in ("MCP_TELEGRAM_BRIDGE_DATA_DIR", "MCP_TELEGRAM_DATA_DIR"):
        override = (os.getenv(key) or "").strip()
        if override:
            return Path(override).expanduser()
    try:
        from platformdirs import user_data_dir  # type: ignore[import-not-found]

        return Path(user_data_dir("mcp-telegram-bridge", appauthor=False))
    except ImportError:
        pass
    xdg_data = (os.getenv("XDG_DATA_HOME") or "").strip()
    if xdg_data:
        return Path(xdg_data).expanduser() / "mcp-telegram-bridge"
    xdg_cache = (os.getenv("XDG_CACHE_HOME") or "").strip()
    if xdg_cache:
        return Path(xdg_cache).expanduser() / "mcp-telegram-bridge"
    return Path.home() / ".local" / "share" / "mcp-telegram-bridge"


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from the environment."""

    bot_token: str
    allowed_chat_ids: frozenset[int] = field(default_factory=frozenset)
    allow_all_chats: bool = False
    data_dir: Path = field(default_factory=_default_data_dir)
    api_base: str = "https://api.telegram.org"
    safety_strict: bool = True
    max_inbound_chars: int = DEFAULT_MAX_INBOUND_CHARS
    max_update_bytes: int = DEFAULT_MAX_UPDATE_BYTES
    inbound_chat_rate: tuple[int, float] | None = DEFAULT_INBOUND_CHAT_RATE
    inbound_global_rate: tuple[int, float] | None = DEFAULT_INBOUND_GLOBAL_RATE
    inbound_poll_rate: tuple[int, float] | None = DEFAULT_INBOUND_POLL_RATE
    outbound_chat_rate: tuple[int, float] | None = DEFAULT_OUTBOUND_CHAT_RATE
    outbound_global_rate: tuple[int, float] | None = DEFAULT_OUTBOUND_GLOBAL_RATE

    @property
    def has_chat_filter(self) -> bool:
        """True when chats are filtered. False only in explicit open mode."""
        return not self.open_mode

    @property
    def open_mode(self) -> bool:
        """True only when open mode is opted in and no allowlist is set."""
        return self.allow_all_chats and not self.allowed_chat_ids

    def chat_allowed(self, chat_id: int) -> bool:
        """Fail closed: an empty allowlist denies every chat.

        ``ALLOW_ALL_CHATS`` opts in to open mode, and only when the allowlist
        is empty. A non-empty allowlist always wins.
        """
        if self.allowed_chat_ids:
            return int(chat_id) in self.allowed_chat_ids
        return self.allow_all_chats

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
            allow_all_chats=_parse_bool(os.getenv("ALLOW_ALL_CHATS")),
            safety_strict=_parse_bool(os.getenv("SAFETY_STRICT"), default=True),
            max_inbound_chars=_parse_bounded_int(
                os.getenv("MAX_INBOUND_CHARS"),
                name="MAX_INBOUND_CHARS",
                default=DEFAULT_MAX_INBOUND_CHARS,
                ceiling=MAX_INBOUND_CHARS_CEILING,
            ),
            max_update_bytes=_parse_bounded_int(
                os.getenv("MAX_UPDATE_BYTES"),
                name="MAX_UPDATE_BYTES",
                default=DEFAULT_MAX_UPDATE_BYTES,
                ceiling=MAX_UPDATE_BYTES_CEILING,
            ),
            inbound_chat_rate=_parse_rate(
                os.getenv("INBOUND_CHAT_RATE"),
                name="INBOUND_CHAT_RATE",
                default=DEFAULT_INBOUND_CHAT_RATE,
            ),
            inbound_global_rate=_parse_rate(
                os.getenv("INBOUND_GLOBAL_RATE"),
                name="INBOUND_GLOBAL_RATE",
                default=DEFAULT_INBOUND_GLOBAL_RATE,
            ),
            inbound_poll_rate=_parse_rate(
                os.getenv("INBOUND_POLL_RATE"),
                name="INBOUND_POLL_RATE",
                default=DEFAULT_INBOUND_POLL_RATE,
            ),
            outbound_chat_rate=_parse_rate(
                os.getenv("OUTBOUND_CHAT_RATE"),
                name="OUTBOUND_CHAT_RATE",
                default=DEFAULT_OUTBOUND_CHAT_RATE,
            ),
            outbound_global_rate=_parse_rate(
                os.getenv("OUTBOUND_GLOBAL_RATE"),
                name="OUTBOUND_GLOBAL_RATE",
                default=DEFAULT_OUTBOUND_GLOBAL_RATE,
            ),
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
