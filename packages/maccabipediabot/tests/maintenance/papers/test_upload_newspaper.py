"""The wiki-side rules of upload_newspaper, with the wiki replaced by a fake ``api()``."""
import hashlib
from argparse import Namespace
from datetime import date

import pytest
from PIL import Image

from maccabipediabot.maintenance.papers import upload_newspaper as tool
from maccabipediabot.maintenance.papers.newspaper_names import NewspaperClip
from maccabipediabot.maintenance.tickets.ticket_names import Sport

GAME = "כדורסל:29-10-1998 הכוכב האדום בלגרד נגד מכבי תל אביב - פיבא יורוליג"
OLD_GAME = "כדורסל: 29-10-1998 הכוכב האדום בלגרד נגד מכבי תל אביב - פיבא יורוליג"  # spaced redirect
FILE = "ידיעות אחרונות 30-10-1998 סיקור משחק כדורסל הכוכב האדום בלגרד (29.10.1998) עמוד 11.jpg"
TEXT = ("{{תיוג עיתוני כדורסל\n|שם עיתון=ידיעות אחרונות\n|תאריך פרסום=30-10-1998\n"
        "|סיווג=סיקור משחק\n|שיוך משחק=" + OLD_GAME + "\n}}")
CLIP = NewspaperClip(paper="ידיעות אחרונות", publish_date=date(1998, 10, 30), classification="סיקור משחק",
                     sport=Sport.BASKETBALL, opponent="הכוכב האדום בלגרד", game_date=date(1998, 10, 29),
                     game_page=GAME)
DATA = b"new crop bytes"


class FakeWiki:
    def __init__(self, files=None, sha1=None, backlinks=(), deleted=(), same_bytes=()):
        self.files = files or {}
        self.sha1 = sha1 or {}
        self.backlinks = backlinks
        self.deleted = set(deleted)
        self.same_bytes = list(same_bytes)

    def __call__(self, **p):
        if p.get("list") == "allimages":
            return {"query": {"allimages": [{"title": t} for t in self.same_bytes]}}
        if p.get("list") == "logevents":
            name = p["letitle"].removeprefix("File:")
            return {"query": {"logevents": [{}] if name in self.deleted else []}}
        if p.get("generator") == "backlinks":
            return {"query": {"pages": [{"title": t, "templates": [{"title": tpl}]} for t, tpl in self.backlinks]}}
        title = p["titles"]
        if p.get("redirects") == 1:
            return {"query": {"pages": [{"title": GAME if title in (GAME, OLD_GAME) else title}]}}
        name = title.removeprefix("File:")
        if p.get("prop") == "revisions":
            if name not in self.files:
                return {"query": {"pages": [{"missing": True}]}}
            return {"query": {"pages": [{"revisions": [{"slots": {"main": {"content": self.files[name]}}}]}]}}
        if p.get("prop") == "imageinfo":
            return {"query": {"pages": [{"imageinfo": [{"sha1": self.sha1[name]}]} if name in self.sha1 else {}]}}
        raise AssertionError(f"unexpected api call {p}")


@pytest.fixture
def wiki(monkeypatch):
    def install(**kwargs):
        fake = FakeWiki(**kwargs)
        monkeypatch.setattr(tool, "api", fake)
        return fake
    return install


def args(**changes):
    base = dict(replace=None, image=None, tier="regular", whole_page_because="")
    return Namespace(**{**base, **changes})


def test_replace_accepts_the_same_piece_linked_through_the_old_title(wiki):
    wiki(files={FILE: TEXT}, sha1={FILE: "old"})
    assert tool.check_replace_target(FILE, GAME, DATA, CLIP) == []


@pytest.mark.parametrize("text, reason", [
    (TEXT.replace("שם עיתון=ידיעות אחרונות", "שם עיתון=מעריב"), "שם עיתון"),
    (TEXT.replace("30-10-1998", "05-11-1998"), "תאריך פרסום"),
    (TEXT.replace("סיווג=סיקור משחק", "סיווג=רגע ממשחק"), "סיווג"),
    (TEXT.replace(OLD_GAME, "כדורסל:01-01-1999 אחר נגד מכבי תל אביב - ליגה"), "linked to"),
    ("[[קטגוריה:תמונות]]", "not a newspaper file"),
])
def test_replace_refuses_a_different_piece(wiki, text, reason):
    wiki(files={FILE: text}, sha1={FILE: "old"})
    assert reason in " ".join(tool.check_replace_target(FILE, GAME, DATA, CLIP))


def test_replace_refuses_the_identical_image(wiki):
    wiki(files={FILE: TEXT}, sha1={FILE: hashlib.sha1(DATA).hexdigest()})
    assert "exactly this image" in " ".join(tool.check_replace_target(FILE, GAME, DATA, CLIP))


def test_linked_files_count_only_newspaper_templates(wiki):
    wiki(backlinks=[("קובץ:א.jpg", "תבנית:תיוג עיתוני כדורסל"), ("קובץ:כרטיס.jpg", "תבנית:תיוג כרטיס משחק כדורסל")])
    assert tool.linked_newspaper_files(GAME) == ["קובץ:א.jpg"]


def test_new_upload_over_the_cap_is_refused(wiki):
    wiki()
    problems = tool.upload_problems(args(), CLIP, CLIP.file_name, GAME, ["קובץ:א.jpg", "קובץ:ב.jpg", "קובץ:ג.jpg"],
                                    Image.new("RGB", (800, 600)), DATA)
    assert any("up to 3" in p for p in problems)


def test_new_upload_refuses_taken_deleted_or_duplicate(wiki):
    wiki(files={CLIP.file_name: TEXT}, deleted=[CLIP.file_name], same_bytes=["קובץ:עותק.jpg"])
    problems = " ".join(tool.upload_problems(args(), CLIP, CLIP.file_name, GAME, [],
                                             Image.new("RGB", (800, 600)), DATA))
    assert "already exists" in problems and "deleted" in problems and "same image" in problems
