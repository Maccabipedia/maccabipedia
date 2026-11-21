"""A stand-in for a wiki's API, shared by the player-titles tests."""
from __future__ import annotations


class FakeCargoApi:
    """Answers `action=cargoquery` from in-memory rows, paging by `limit` and `offset`.

    `tables` maps the `tables` parameter of a query to its rows. A query whose `fields`
    is a COUNT answers with `counts[tables]`, or with the true number of rows.
    """

    def __init__(self, tables: dict[str, list[dict]], counts: dict[str, int] | None = None):
        self.tables = tables
        self.counts = counts or {}
        self.calls: list[dict] = []

    def __call__(self, **params) -> dict:
        self.calls.append(params)
        assert params["action"] == "cargoquery", params
        rows = self.tables[params["tables"]]
        if params["fields"].startswith("COUNT("):
            count = self.counts.get(params["tables"], len(rows))
            return {"cargoquery": [{"title": {"n": str(count)}}]}

        offset, limit = int(params.get("offset", 0)), int(params["limit"])
        return {"cargoquery": [{"title": row} for row in rows[offset:offset + limit]]}

    def data_calls(self) -> list[dict]:
        return [call for call in self.calls if not call["fields"].startswith("COUNT(")]
