#!/usr/bin/env python3
"""Print a trimmed view of a Trello list's cards (idShort, name, labels).

Context-friendly replacement for the trello MCP's get_cards_by_list_id (no field
filtering, banned in CLAUDE.md). Full JSON is saved to .claude/tmp/. See
.claude/trello.md.

Usage:
    uv run python .claude/scripts/trello_list.py <listId>
"""
import sys

from trello_common import format_labels, save_full, trello_get


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: trello_list.py <listId>")
    list_id = sys.argv[1]

    cards = trello_get(
        f"lists/{list_id}/cards", {"fields": "name,labels,idShort"}
    )
    out_path = save_full(f"trello_list_{list_id}", cards)

    for card in cards:
        print(f"#{card['idShort']}  {card['name']}  [{format_labels(card)}]")
    print(f"\n{len(cards)} cards — full JSON saved to {out_path}")


if __name__ == "__main__":
    main()
