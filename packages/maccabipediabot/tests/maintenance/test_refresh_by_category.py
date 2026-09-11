"""Unit tests for the football refresh_by_category maintenance job."""
from unittest.mock import MagicMock, patch

import pytest
from pywikibot.exceptions import TimeoutError as PwbTimeoutError

from maccabipediabot.maintenance.football import refresh_by_category as refresh

MODULE = "maccabipediabot.maintenance.football.refresh_by_category"


def _page(title: str) -> MagicMock:
    page = MagicMock()
    page.title.return_value = title
    return page


class TestResolveRecentSeasons:
    @patch(f"{MODULE}.cargo_query")
    def test_returns_seasons_newest_first(self, mock_cargo):
        mock_cargo.return_value = [
            {"Season": "2026/27", "LastDate": "2026-07-16"},
            {"Season": "2025/26", "LastDate": "2026-05-26"},
        ]

        assert refresh.resolve_recent_seasons(MagicMock(), count=2) == ["2026/27", "2025/26"]
        assert mock_cargo.call_args.kwargs["limit"] == 2

    @patch(f"{MODULE}.cargo_query")
    def test_raises_when_no_games_exist(self, mock_cargo):
        mock_cargo.return_value = []

        with pytest.raises(RuntimeError):
            refresh.resolve_recent_seasons(MagicMock(), count=2)


class TestCollectSeasonPlayers:
    @patch(f"{MODULE}.pywikibot")
    @patch(f"{MODULE}.cargo_query")
    def test_queries_every_season_and_only_maccabi(self, mock_cargo, mock_pw):
        mock_cargo.return_value = [{"PlayerName": "דור פרץ"}, {"PlayerName": "שרן ייני"}]
        mock_pw.Page.side_effect = lambda _site, title: _page(title)

        pages = refresh.collect_season_players(MagicMock(), ["2026/27", "2025/26"])

        where = mock_cargo.call_args.kwargs["where"]
        # Both seasons must be in the IN clause, and opponents excluded.
        assert "'2026/27'" in where and "'2025/26'" in where
        assert f"e.Team={refresh.MACCABI_TEAM_ID}" in where
        assert [p.title() for p in pages] == ["דור פרץ", "שרן ייני"]

    @patch(f"{MODULE}.pywikibot")
    @patch(f"{MODULE}.cargo_query")
    def test_skips_rows_without_a_player_name(self, mock_cargo, mock_pw):
        mock_cargo.return_value = [{"PlayerName": "דור פרץ"}, {}]
        mock_pw.Page.side_effect = lambda _site, title: _page(title)

        assert len(refresh.collect_season_players(MagicMock(), ["2025/26"])) == 1


class TestPurgeInBatches:
    @patch(f"{MODULE}.purge_pages")
    def test_splits_into_batches_covering_every_page(self, mock_purge):
        # 25 pages at BATCH_SIZE=10 -> 3 batches (10/10/5), no page dropped.
        pages = [_page(f"שחקן {i}") for i in range(25)]
        mock_purge.side_effect = lambda _site, batch, **_kw: len(list(batch))

        failed = refresh.purge_in_batches(MagicMock(), pages, dry_run=False)

        assert failed == 0
        assert mock_purge.call_count == 3
        batched = [p for call in mock_purge.call_args_list for p in call.args[1]]
        assert batched == pages

    @patch(f"{MODULE}.purge_pages")
    def test_timeout_in_one_batch_does_not_abort_the_sweep(self, mock_purge):
        pages = [_page(f"שחקן {i}") for i in range(25)]
        # First batch times out the way the live 801-page run did; rest succeed.
        mock_purge.side_effect = [PwbTimeoutError("Maximum retries attempted"), 10, 5]

        failed = refresh.purge_in_batches(MagicMock(), pages, dry_run=False)

        assert mock_purge.call_count == 3
        assert failed == 1

    @patch(f"{MODULE}.purge_pages")
    def test_unexpected_errors_still_propagate(self, mock_purge):
        # Only server/timeout errors are tolerated — real bugs must stay visible.
        mock_purge.side_effect = ValueError("boom")

        with pytest.raises(ValueError):
            refresh.purge_in_batches(MagicMock(), [_page("אבי כהן")], dry_run=False)


@patch(f"{MODULE}.get_site")
@patch(f"{MODULE}.setup_logging")
class TestMain:
    @patch(f"{MODULE}.purge_in_batches", return_value=0)
    @patch(f"{MODULE}.collect_season_players")
    @patch(f"{MODULE}.resolve_recent_seasons", return_value=["2026/27", "2025/26"])
    def test_defaults_to_recent_seasons(
        self, mock_resolve, mock_collect, mock_purge, _log, _site
    ):
        players = [_page("דור פרץ")]
        mock_collect.return_value = players

        rc = refresh.main(
            dry_run=True, refresh_all=False, category="פרופילי כדורגל",
            season=None, recent_seasons=2,
        )

        assert rc == 0
        mock_resolve.assert_called_once()
        assert mock_collect.call_args.args[1] == ["2026/27", "2025/26"]
        assert mock_purge.call_args.args[1] == players

    @patch(f"{MODULE}.purge_in_batches", return_value=0)
    @patch(f"{MODULE}.collect_season_players")
    @patch(f"{MODULE}.resolve_recent_seasons")
    def test_explicit_season_skips_resolution(
        self, mock_resolve, mock_collect, _purge, _log, _site
    ):
        mock_collect.return_value = [_page("דור פרץ")]

        refresh.main(
            dry_run=True, refresh_all=False, category="פרופילי כדורגל",
            season="2024/25", recent_seasons=2,
        )

        mock_resolve.assert_not_called()
        assert mock_collect.call_args.args[1] == ["2024/25"]

    @patch(f"{MODULE}.purge_in_batches", return_value=0)
    @patch(f"{MODULE}.collect_members")
    @patch(f"{MODULE}.collect_season_players")
    def test_all_flag_sweeps_the_whole_category(
        self, mock_season, mock_members, mock_purge, _log, _site
    ):
        everyone = [_page("אבי כהן"), _page("אורי מלמיליאן")]
        mock_members.return_value = everyone

        refresh.main(
            dry_run=False, refresh_all=True, category="פרופילי כדורגל",
            season=None, recent_seasons=2,
        )

        mock_season.assert_not_called()
        assert mock_purge.call_args.args[1] == everyone

    @patch(f"{MODULE}.purge_in_batches", return_value=2)
    @patch(f"{MODULE}.collect_season_players", return_value=[])
    @patch(f"{MODULE}.resolve_recent_seasons", return_value=["2026/27"])
    def test_failed_batches_surface_as_exit_code(self, _resolve, _collect, _purge, _log, _site):
        rc = refresh.main(
            dry_run=False, refresh_all=False, category="פרופילי כדורגל",
            season=None, recent_seasons=1,
        )

        assert rc == 1
