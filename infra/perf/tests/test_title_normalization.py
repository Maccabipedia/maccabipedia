"""existing_titles must survive MediaWiki's title normalization."""
from wiki_api import DEFAULT_OUT_DIR, REPO_ROOT, WikiApi


class FakeResponse:
    status_code = 200
    headers = {"Content-Type": "application/json; charset=utf-8"}

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    """Stands in for requests.Session; records nothing, returns one payload."""

    headers: dict[str, str] = {}

    def __init__(self, payload):
        self._payload = payload

    def get(self, *_args, **_kwargs):
        return FakeResponse(self._payload)


def _api_returning(payload) -> WikiApi:
    api = WikiApi(pace_seconds=0.0)
    api.session = FakeSession(payload)
    return api


def test_a_normalized_title_is_reported_under_the_caller_s_own_spelling():
    # Asked for "שרן_ייני" (underscore, as a Cargo value might carry); the API
    # answers about "שרן ייני" and explains the mapping under `normalized`.
    api = _api_returning({
        "query": {
            "normalized": [{"from": "שרן_ייני", "to": "שרן ייני"}],
            "pages": [{"title": "שרן ייני"}],
        }
    })
    found = api.existing_titles(["שרן_ייני"])
    assert "שרן_ייני" in found, "caller's spelling must match, or the page reads as missing"
    assert "שרן ייני" in found


def test_missing_and_invalid_pages_are_excluded():
    api = _api_returning({
        "query": {
            "pages": [
                {"title": "אבי כהן"},
                {"title": "לא קיים", "missing": True},
                {"title": "<bad>", "invalid": True},
            ]
        }
    })
    assert api.existing_titles(["אבי כהן", "לא קיים", "<bad>"]) == {"אבי כהן"}


def test_default_output_dir_is_ignored_by_git():
    # .gitignore's `.claude/tmp/` is anchored to the repo root, so a default
    # resolved against the working directory would leave untracked files behind
    # after every run.
    assert DEFAULT_OUT_DIR == REPO_ROOT / ".claude" / "tmp" / "perf"
    assert (REPO_ROOT / ".gitignore").exists(), "REPO_ROOT should be the repo root"
