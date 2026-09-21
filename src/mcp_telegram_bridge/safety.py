"""Optional inbound classification and always-on outbound scrubbing."""

from __future__ import annotations

import os
import re
from typing import Any, Literal

Kind = Literal["secrets", "adult", "ok"]

# Asking about *real* infrastructure / credentials / private ids.
_SECRETS_ASK = re.compile(
    r"""(?ix)
    (
      \b(api[_\s-]?key|access[_\s-]?token|bot\s*token|telegram[_\s-]?token|
         webhook\s*key|webhook\s*url|whsec_|crsr_|
         dotenv|admin_telegram|allowed_chat_ids|
         private[_\s-]?key|ssh[_\s-]?key)\b
      |
      (?<!\w)\.env(?!\w)
      |
      \b(password|passwd|passwort|contrase[nñ]a|mot\s*de\s*passe|secret|credential|token|clave)\b
        .{0,48}\b(bot|telegram|admin|account|webhook|server|vm|bridge|token|api|env)\b
      |
      \b(bot|telegram|admin|account|webhook|server|vm|bridge|api|env)\b
        .{0,48}\b(password|passwd|contrase[nñ]a|secret|credential|token|clave)\b
      |
      \b(dame|show|give|leak|exfiltrat|cat|print|dump)\b.{0,40}(\.env\b|dotenv|token|password|secret|clave|webhook)
      |
      \b(admin[_\s-]?id|telegram[_\s-]?id\s+de\s+admin)\b
    )
    """,
)

_ADULT_ASK = re.compile(
    r"""(?ix)
    \b(
      porn|porno|xxx|nsfw|onlyfans|
      nude|nudes|nudity|desnudo|desnuda|nackt|
      erotic|er[oó]tic[oa]|sex\s*story|historia\s*er[oó]tica|
      hardcore|hentai|rule34|
      blowjob|handjob|cumshot|anal\s*sex|orgasm|
      foll[ae]r|coger\b|polvo\b|putas?\b|
      child\s*porn|csam|underage\s*sex|menor(es)?\s*(desnud|sex)
    )\b
    """,
)

_TOKENISH = re.compile(
    r"""(?x)
    \b(gh[pousr]_[A-Za-z0-9_]{20,}|
       xox[baprs]-[A-Za-z0-9-]{10,}|
       whsec_[A-Za-z0-9+/=_-]{16,}|
       crsr_[A-Za-z0-9_]{16,}|
       sk-[A-Za-z0-9]{20,}|
       \d{8,12}:[A-Za-z0-9_-]{30,})\b
    """
)

_ENV_NAMES = (
    "TELEGRAM_BOT_TOKEN",
    "MESA_WAKE_URL",
    "MESA_WAKE_KEY",
    "ADMIN_TELEGRAM_IDS",
    "ALLOWED_CHAT_IDS",
)

_ENV_ASSIGNMENT = re.compile(
    r"(?im)(?<![A-Za-z0-9_])((?:export\s+)?[A-Z][A-Z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD|PASSWD|CREDENTIAL|WEBHOOK|PRIVATE|ADMIN|CHAT_IDS|WAKE_URL|WAKE_KEY)[A-Z0-9_]*)\s*=\s*([\"']?)([^\s\"']+)\2"
)

_WEBHOOK_URL = re.compile(
    r"https?://[^\s]+(?:webhook|whsec_|hook)[^\s]*",
    flags=re.I,
)


def classify_inbound(text: str) -> Kind:
    """Classify inbound user/agent-facing text."""
    raw = text or ""
    if _ADULT_ASK.search(raw):
        return "adult"
    if _SECRETS_ASK.search(raw):
        return "secrets"
    return "ok"


# Back-compat alias used by sibling demos.
classify_player_text = classify_inbound


def refusal(kind: Kind, lang: str = "en") -> str:
    """Human-facing refusal copy for blocked inbound kinds."""
    lang = (lang or "en").lower()[:2]
    if kind == "adult":
        msg = {
            "es": "Este canal no admite contenido sexual ni NSFW.",
            "en": "This channel does not allow sexual or NSFW content.",
            "fr": "Ce canal n'autorise pas le contenu sexuel ni NSFW.",
            "de": "Dieser Kanal erlaubt keine sexuellen oder NSFW-Inhalte.",
        }
        return msg.get(lang, msg["en"])
    if kind == "secrets":
        msg = {
            "es": "No discuto contraseñas, tokens, ids internos ni detalles de conexión del sistema.",
            "en": "I do not discuss passwords, tokens, internal ids, or system connection details.",
            "fr": "Je ne discute pas mots de passe, tokens, ids internes ni détails de connexion système.",
            "de": "Ich bespreche keine Passwörter, Tokens, interne IDs oder System-Verbindungsdaten.",
        }
        return msg.get(lang, msg["en"])
    return ""


def _secret_values() -> list[str]:
    out: list[str] = []
    for name in _ENV_NAMES:
        val = (os.getenv(name) or "").strip()
        if len(val) >= 4:
            out.append(val)
    return out


def scrub_outbound(text: str) -> str:
    """Redact env secrets and token-shaped strings before Telegram send."""
    if not text:
        return text
    scrubbed = text
    for val in _secret_values():
        if val and val in scrubbed:
            scrubbed = scrubbed.replace(val, "[REDACTED]")
    scrubbed = _TOKENISH.sub("[REDACTED]", scrubbed)
    scrubbed = _ENV_ASSIGNMENT.sub(r"\1=[REDACTED]", scrubbed)
    scrubbed = _WEBHOOK_URL.sub("[REDACTED-URL]", scrubbed)
    return scrubbed


def annotate_inbound_text(text: str) -> dict[str, Any]:
    """Return a structured view of inbound text for tool results.

    Never silently drop: the agent always sees ``blocked`` / ``warning`` /
    ``kind`` when content is flagged.
    """
    kind = classify_inbound(text or "")
    if kind == "ok":
        return {
            "text": text,
            "kind": "ok",
            "blocked": False,
            "warning": None,
        }
    return {
        "text": text,
        "kind": kind,
        "blocked": True,
        "warning": refusal(kind),
        "redacted_preview": (text or "")[:80],
    }


def annotate_update(update: dict[str, Any]) -> dict[str, Any]:
    """Annotate a Telegram update dict with inbound safety fields."""
    out = dict(update)
    texts: list[str] = []
    msg = update.get("message") or update.get("edited_message") or {}
    if isinstance(msg, dict) and msg.get("text"):
        texts.append(str(msg["text"]))
    cb = update.get("callback_query") or {}
    if isinstance(cb, dict):
        if cb.get("data"):
            texts.append(str(cb["data"]))
        cb_msg = cb.get("message") or {}
        if isinstance(cb_msg, dict) and cb_msg.get("text"):
            texts.append(str(cb_msg["text"]))
    blob = "\n".join(texts)
    safety = annotate_inbound_text(blob)
    out["safety"] = {
        "kind": safety["kind"],
        "blocked": safety["blocked"],
        "warning": safety["warning"],
    }
    return out
