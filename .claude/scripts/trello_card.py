#!/usr/bin/env python3
"""Print a trimmed view of one Trello card, resolved by its short number.

Context-friendly replacement for the trello MCP's get_card. Full JSON (including
all checklist items) is saved to .claude/tmp/. See .claude/trello.md.

Usage:
    uv run python .claude/scripts/trello_card.py <cardNumber>
"""
import sys

from trello_common import format_labels, load_creds, save_full, trello_get


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: trello_card.py <cardNumber>")
    number = sys.argv[1]
    _, _, board_id = load_creds()

    card = trello_get(
        f"boards/{board_id}/cards/{number}",
        {"fields": "name,labels,desc,url,idList", "checklists": "all"},
    )
    out_path = save_full(f"trello_card_{number}", card)

    list_name = "?"
    if card.get("idList"):
        list_name = trello_get(f"lists/{card['idList']}", {"fields": "name"})["name"]
    print(f"#{number}  {card['name']}  [{format_labels(card)}]")
    print(f"list: {list_name}")
    print(f"url:  {card.get('url', '')}")
    if card.get("desc"):
        print(f"\ndesc:\n{card['desc']}")
    for checklist in card.get("checklists", []):
        print(f"\nchecklist: {checklist['name']}")
        for item in checklist.get("checkItems", []):
            mark = "x" if item["state"] == "complete" else " "
            print(f"  [{mark}] {item['name']}")
    print(f"\nfull JSON saved to {out_path}")


if __name__ == "__main__":
    main()
