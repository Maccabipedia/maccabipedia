"""Shared helpers for the trello_*.py read scripts.

Reads = scripts (this family); writes = the trello MCP. See .claude/trello.md.

These scripts exist because the third-party trello MCP's read tools have no field
filtering: they dump the full ~40K-char card JSON, and MCP output cannot be
redirected to a file. A curl can. So every read here saves the full JSON to
.claude/tmp/ and prints only a trimmed view, keeping the model's context small.
"""
import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
TMP_DIR = REPO / ".claude" / "tmp"


def load_creds():
    config = json.loads((REPO / ".mcp.json").read_text())
    env = config["mcpServers"]["trello"]["env"]
    return env["TRELLO_API_KEY"], env["TRELLO_TOKEN"], env["TRELLO_BOARD_ID"]


def trello_get(path, extra_params=None):
    """GET https://api.trello.com/1/<path> with auth, returning parsed JSON."""
    api_key, token, _ = load_creds()
    params = {"key": api_key, "token": token}
    if extra_params:
        params.update(extra_params)
    url = f"https://api.trello.com/1/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
    except urllib.error.HTTPError as error:
        # error.url / error.filename carry the secret-bearing URL (key+token);
        # never surface them — report only the status and the safe path.
        raise RuntimeError(
            f"Trello GET /{path} failed: HTTP {error.code} {error.reason}"
        ) from None
    if "application/json" not in content_type:
        raise RuntimeError(
            f"Trello GET /{path} returned non-JSON ({content_type or 'unknown'})"
        )
    return json.loads(body)


def save_full(name, data):
    """Save full JSON to .claude/tmp/<name>.json and return the path."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TMP_DIR / f"{name}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return out_path


def format_labels(card):
    return ", ".join(
        label.get("name") for label in card.get("labels", []) if label.get("name")
    )
