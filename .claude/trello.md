# Talking to Trello

The board is **MaccabiPedia** (`https://trello.com/b/n9Zz1CSL`). Credentials
(`TRELLO_API_KEY`, `TRELLO_TOKEN`, `TRELLO_BOARD_ID`) live in `.mcp.json` under
`mcpServers.trello.env`.

## The rule: reads = scripts, writes = MCP

| Operation | Use | Why |
|-----------|-----|-----|
| **Read** a list, a card, the board | `.claude/scripts/trello_*.py` | MCP read tools have no field filtering and dump the full ~40K-char card JSON. MCP output **cannot be redirected to a file** — it always lands in context. A script `curl`s, saves full JSON to `.claude/tmp/`, and prints only a trimmed view. |
| **Write** — add/move/update/archive a card, add a comment or checklist item | trello MCP (`mcp__trello__*`) | Write responses are small, and the MCP handles auth + board context. No reason to reimplement. |

This is why `get_cards_by_list_id` and `get_card` are effectively banned for reads
(see CLAUDE.md §6).

## Read scripts

All share `trello_common.py` (cred loading, authenticated GET, save-to-tmp,
label formatting). Run with `uv run`:

```
uv run python .claude/scripts/trello_list.py <listId>     # cards in a list: idShort, name, labels
uv run python .claude/scripts/trello_card.py <cardNumber> # one card: name, labels, list, url, desc, checklists
```

Each prints a trimmed view and saves the full JSON to
`.claude/tmp/trello_list_<id>.json` / `trello_card_<number>.json` for when you
need a field the trimmed view dropped.

## Finding IDs

- **List IDs** — `mcp__trello__get_lists` returns all lists with their IDs (small
  response, safe to call). Current board lists: Waiting, Backlog, **Next Up**,
  In Progress, Done, For the far future, Road map.
- **Card numbers** — the `#NNN` shown by `trello_list.py`, or the number in a card
  URL (`/c/<hash>/<number>-...`). `trello_card.py` resolves a card by number via
  `/boards/{boardId}/cards/{number}`.

## Gotchas (also in memory)

- `move_card` needs `boardId` passed explicitly — the "default" fallback returns 400.
- The `list=true` embed param is **not** honored on the board-scoped card endpoint;
  request `idList` and resolve the list name separately (what `trello_card.py` does).
- If the MCP itself is down, the read scripts still work (pure REST); for writes,
  fall back to the Trello REST API with the same `.mcp.json` creds.
