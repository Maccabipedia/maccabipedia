from maccabipediabot.common.wiki_purge import purge_pages


class StubSite:
    """Records every purgepages call so tests can assert on batching."""

    def __init__(self, return_value: bool = True):
        self.calls: list[tuple[list[str], dict]] = []
        self._return_value = return_value

    def purgepages(self, pages, **kwargs):
        self.calls.append((list(pages), kwargs))
        return self._return_value


class StubPage:
    """Minimal stand-in for a pywikibot Page (only .title() is used)."""

    def __init__(self, title: str):
        self._title = title

    def title(self) -> str:
        return self._title


def test_empty_input_makes_no_call():
    site = StubSite()
    assert purge_pages(site, []) == 0
    assert site.calls == []


def test_dedups_and_sorts_titles():
    site = StubSite()
    submitted = purge_pages(site, ["מוטל'ה שפיגלר", "אבי כהן", "אבי כהן"])
    assert submitted == 2
    assert len(site.calls) == 1
    titles, kwargs = site.calls[0]
    assert titles == ["אבי כהן", "מוטל'ה שפיגלר"]
    assert kwargs == {"forcelinkupdate": True}


def test_page_objects_and_strings_dedup_by_title():
    site = StubSite()
    submitted = purge_pages(site, [StubPage("ערן זהבי"), "ערן זהבי", StubPage("טל ברודי")])
    assert submitted == 2
    titles, _ = site.calls[0]
    assert titles == ["טל ברודי", "ערן זהבי"]


def test_chunks_respect_chunk_size():
    site = StubSite()
    pages = [f"page-{index:03d}" for index in range(120)]
    submitted = purge_pages(site, pages, chunk_size=50)
    assert submitted == 120
    assert [len(titles) for titles, _ in site.calls] == [50, 50, 20]


def test_dry_run_submits_nothing():
    site = StubSite()
    submitted = purge_pages(site, ["אבי כהן", "ערן זהבי"], dry_run=True)
    assert submitted == 2
    assert site.calls == []
