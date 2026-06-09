# Maccabipedia MediaWiki Bot — Claude Code Guide

## 1. Script Execution
- **NEVER use `python3 -c`**, `python -c`, or any inline Python. No exceptions. Not even one-liners.
- **NEVER use multiline bash commands**, heredocs (`<< 'EOF'`), or commands containing `#` comments.
- **Always write scripts and temp data to files**, not inline. Use the Write tool to create the file, then `Bash` to run it. With worktrees, each session has its own working directory so files stay isolated.
- To open files/URLs: `bash .claude/scripts/open-in-browser.sh <url-or-path>`

## 2. Environment
- Running scripts requires `MACCABIPEDIA_UA_SCRIPT` env var — set in `settings.json` env. Pywikibot reads credentials from `user-password.py` directly; never use `source ~/.secrets`.
- **Always use `uv run` instead of running commands directly** — e.g. `uv run python`, `uv run pytest`, `uv run mypy`. This auto-detects the local `.venv` without activation. Works in both the main repo and worktrees.

## 3. Git Workflow
- **Always work on a feature branch.** Nothing is committed directly to `master`; everything goes through a PR.
- **Use worktrees** for feature branches to avoid collisions between parallel sessions. Hooks in `.claude/hooks/` automatically create worktrees at `../maccabipedia_mediawikibot-wt/<name>/` with config and venv.
- Before any `git add`, run `git status` and review every file. Only stage files directly related to the current task.

### Commit Message Format
All commits use **Conventional Commits** with a scope: `type(scope): description`

| Scope | Covers |
|---|---|
| `maccabistats` | `packages/maccabistats/` |
| `mcp` | `packages/maccabipedia-mcp/` |
| `football` | `maccabipediabot/football/` |
| `volleyball` | `maccabipediabot/volleyball/` |
| `basketball` | `maccabipediabot/basketball/` |
| `maintenance` | `maccabipediabot/maintenance/` (videos, papers, etc.) |
| `calendar` | `maccabipediabot/calendar/` |
| `ci` | `.github/workflows/` |
| `dev` | `pyproject.toml`, `CLAUDE.md`, settings, tooling, `common/`, `pywikibot_configs/` |

Examples: `fix(maintenance): treat HTTP 400 from oEmbed as broken video`, `feat(maccabistats): add best_scorers_in_one_game`

## 4. Lessons Learned

### Always validate API responses before parsing
Cargo Export returns HTML error pages on internal errors — not JSON. Always check `response.status_code == 200` and `'application/json' in response.headers.get('Content-Type', '')` before calling `.json()`. Log the raw response on failure.

### Use football bot as reference template for other sports
When implementing a feature for volleyball/basketball, always inspect the equivalent football implementation first and use it as the reference.

### Hebrew files opened in Windows apps need UTF-8 BOM
Use `utf-8-sig` encoding when writing CSV/TXT/JSON files with Hebrew text that may be opened in Excel or other Windows apps.

### Never use pywikibot's file_page.upload() — use requests directly
Produces malformed HTTP (bad MIME headers, LF-only line endings) → Apache 400. Use `requests.post(..., files=...)` with pywikibot session cookies. Reference: `upload_basketball_tickets.py` → `_upload_file_via_requests()`.

## 5. Workflows

### PR Workflow (all PRs)

**Before creating any PR:**
- No merge conflicts with `master`
- `uv run pytest` passes
- `uv run mypy` has no new type errors
- PR description includes what changed and why

**After PR is created:**
- Monitor CI — if checks fail, fix and push before notifying the user
- User reviews and merges

### maccabistats Version Bump (maccabistats PRs only)

Any PR touching `packages/maccabistats/` must also include, before the PR is created:

1. **Version bump** — update `packages/maccabistats/src/maccabistats/version.py`:
   - New feature or fix → increment minor version (`2.X` → `2.X+1`)
   - Small patch → increment patch version (`2.X.Y` → `2.X.Y+1`)
2. **Changelog entry** — prepend a new entry to `packages/maccabistats/CHANGELOG.md` with the new version and a short description
3. **Commit both** on the feature branch (e.g. `bump: maccabistats 2.61`)

### Skin Version Bump (skins/Maccabipedia/ PRs only)

Any PR changing `skins/Maccabipedia/` must bump `"version"` in
`skins/Maccabipedia/skin.json`. The `skin_version_bump` CI check enforces this
on PRs. MediaWiki surfaces the version on `Special:Version`, so the bump is how
the `deploy-skin` skill verifies prod actually received the new skin.

## 6. Context Window Hygiene

Every tool call result stays in context forever. Keep all outputs small:

- **Explore agents**: always instruct them to write findings to `.claude/tmp/explore_<topic>.md` and return only a 3–5 line summary. Never ask for "comprehensive" or "thorough" reports that return inline.
- **Subagent results**: any Agent call should write its output to `.claude/tmp/` and return a brief summary — not the full analysis inline.
- **Write vs Edit**: never use Write to modify an existing file — Edit sends only the diff. Only use Write for new files, and avoid writing files larger than ~100 lines in one shot; break them up.
- **Bash outputs**: if a script produces more than ~50 lines, redirect verbose output to a temp file and print only the final result.
- **Trello reads vs writes**: writes use the MCP (`add_card`, `add_comment`, `move_card`, …); reads use the `.claude/scripts/trello_*.py` helpers, never the MCP read tools. MCP output can't be redirected to a file, so `get_cards_by_list_id`/`get_card` dump full card JSON (~40K chars) straight into context. The scripts save full JSON to `.claude/tmp/` and print a trimmed view. See `.claude/trello.md`.
- **Knowledge files** (`.claude/*.md`): never Read the whole file. Use Grep to find the relevant section, then Read only those lines.

## 7. Reference Files
- `.claude/maccabipedia_structure_knowledge.md` — Game pages, player pages, templates, Cargo API
- `.claude/maccabipedia_research_sources.md` — External data sources: rosters, match results, historical records, photos, video
- `.claude/maccabistats_knowledge.md` — maccabistats Python package API reference
- `.claude/maccabipedia_youtube_channel.md` — MaccabiPedia YouTube channel conventions + Google Drive backup layout (used by `restore_deleted_football_video`)
- Prod deploys → the `deploy-skin` and `deploy-localsettings` skills (`.claude/skills/`). Skin = `skins/Maccabipedia/` via snapshot + manual FileZilla upload; LocalSettings = `infra/local-wiki/config/LocalSettings.shared.php` only (never `env.prod.php`). FTP creds in `infra/local-wiki/.env`.
- `.claude/trello.md` — Trello convention: reads via `.claude/scripts/trello_*.py` (save full JSON to tmp, print trimmed), writes via the MCP; why; how to find list/board IDs
- `infra/local-wiki/` boots self-contained: `docker compose up -d --build` renders the skin with no prod fetch. Third-party extensions are SHA-pinned in `infra/local-wiki/extensions.json` and cloned into the image at build time (`fetch-extensions.sh`); bump a pin by editing its `ref` and running `uv run python scripts/resolve_extension_pins.py`. Pulling real wiki pages into the local wiki is optional via `download-pages-from-prod.sh` (HTTP `Special:Export` → `downloaded-pages/` → `seed-content.sh`).
