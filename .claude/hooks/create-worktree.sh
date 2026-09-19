#!/usr/bin/env bash
# WorktreeCreate hook — creates worktree at sibling directory with config and venv
#
# Receives JSON on stdin with: cwd, worktree_path, session_id
# Must output the actual worktree path to stdout

set -euo pipefail

INPUT=$(cat)
REPO_ROOT=$(echo "$INPUT" | jq -r '.cwd')
WORKTREE_NAME=$(echo "$INPUT" | jq -r '.name')

REPO_NAME=$(basename "$REPO_ROOT")
WT_ROOT="$(dirname "$REPO_ROOT")/${REPO_NAME}-wt"
WT_DIR="${WT_ROOT}/${WORKTREE_NAME}"

if [ -d "$WT_DIR" ]; then
    echo "$WT_DIR"
    exit 0
fi

mkdir -p "$WT_ROOT"

# Cut from origin/master, not the main clone's HEAD. PRs merge on GitHub and nothing
# fast-forwards the main clone afterwards, so its HEAD drifts — on 2026-09-19 it was 8 commits
# behind and every new session missed the finish-session rule merged that morning (#199).
# A failed fetch (offline) must not stop a session opening: fall back to the last-fetched
# origin/master, and to HEAD only if that ref does not exist at all.
# --no-track keeps what cutting from HEAD gave: no upstream until the session's own `push -u`.
git -C "$REPO_ROOT" fetch -q origin master >&2 \
    || echo "create-worktree: fetch failed — cutting from the last-fetched origin/master" >&2
BASE=origin/master
git -C "$REPO_ROOT" rev-parse -q --verify "$BASE" >/dev/null || BASE=HEAD
git -C "$REPO_ROOT" worktree add --no-track -b "$WORKTREE_NAME" "$WT_DIR" "$BASE" >&2

# Copy gitignored .claude config
SRC="${REPO_ROOT}/.claude/settings.local.json"
if [ -f "$SRC" ]; then
    mkdir -p "${WT_DIR}/.claude"
    cp "$SRC" "${WT_DIR}/.claude/settings.local.json"
fi

# Copy MCP config (gitignored, lives at repo root)
MCP_SRC="${REPO_ROOT}/.mcp.json"
if [ -f "$MCP_SRC" ]; then
    cp "$MCP_SRC" "${WT_DIR}/.mcp.json"
fi

# Copy calendar .env (gitignored, has Google/API credentials)
CAL_ENV="${REPO_ROOT}/packages/maccabipediabot/src/maccabipediabot/calendar/.env"
if [ -f "$CAL_ENV" ]; then
    cp "$CAL_ENV" "${WT_DIR}/packages/maccabipediabot/src/maccabipediabot/calendar/.env"
fi

# Copy local-wiki .env (gitignored, has prod FTP credentials)
LW_ENV="${REPO_ROOT}/infra/local-wiki/.env"
if [ -f "$LW_ENV" ]; then
    mkdir -p "${WT_DIR}/infra/local-wiki"
    cp "$LW_ENV" "${WT_DIR}/infra/local-wiki/.env"
    chmod 600 "${WT_DIR}/infra/local-wiki/.env"
fi

# Create independent venv with packages (uv is ~10x faster than pip)
if [ ! -e "${WT_DIR}/.venv" ]; then
    uv sync --directory "${WT_DIR}" >&2
fi

# Output the worktree path (required by Claude Code)
echo "$WT_DIR"
