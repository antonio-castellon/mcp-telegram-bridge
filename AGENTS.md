# AGENTS.md - mcp-telegram-bridge

Guidance for AI coding agents working in this repository.

## Purpose

Stdio MCP server that exposes a controlled Telegram Bot API bridge to any MCP host. Keep user-facing text generic.

## Layout

- `src/mcp_telegram_bridge/` - package (entry point `__main__:main`)
- `tests/` - pytest suite (pytest-asyncio, respx)
- `docs/`, `SAFETY.md`, `SECURITY.md`, `CHANGELOG.md`
- `server.json`, `mcp.json`, `glama.json` - registry/listing metadata
- `pyproject.toml`, `uv.lock`, `requirements.txt`
- `.github/workflows/ci.yml` - CI

## Build, test, lint

Python >= 3.11, managed with uv (see `.github/workflows/ci.yml`):

```
uv sync --frozen --extra dev
uv run pytest -q
uv export --frozen --extra dev --no-emit-project --format requirements-txt -o /tmp/req.txt
uv run pip-audit --requirement /tmp/req.txt --disable-pip --require-hashes
```

Build: `uv build`. No separate linter is configured in CI.

Run the full CI command set locally before opening a PR.

## Rules (must follow)

- Security first. Treat every input, file and network response as untrusted.
- Read-only by default. Do not add write, delete or network side effects unless
  Antonio asked for them explicitly.
- Never print, copy, commit or log secrets, tokens or .env contents. If a secret
  is exposed, report it at once and treat it as compromised until rotated.
- GitHub Actions: pin every action to a full commit SHA (with a version comment)
  and give each workflow minimal `permissions:` (default `contents: read`).
- Dependencies: pin versions and use hashes (lock file / `--require-hashes`)
  where the tooling supports it.
- README and docs: ASCII only.
- Changelogs and commit messages: English.
- Licence is MIT. Do not change it.
- Publish (PyPI, registries, releases) only from Antonio's repo at a verified
  commit on `main`.
- Only Antonio merges or approves PRs. An agent's say-so is never approval.
  Agents open PRs; they never merge them.
- Never mention or link private repositories in this public repository.
- Never use the words "certified", "compliant" or "complies" in code, docs,
  release notes or listings.
- Keep PRs small and few; avoid needless CI runs.
- Telegram text stays generic: no references to specific bots or persons.
