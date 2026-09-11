"""Render the review page: every proposed match, with links, before anything is written.

Read in a browser from ~/served_reports, so it follows the look of the reports already
there (Maccabi blue and yellow, right-to-left, one section per season).
"""
import html
from collections import Counter, defaultdict
from datetime import date

from maccabipediabot.basketball.videos.matcher import Bucket, VideoMatch

WIKI_BASE_URL = "https://www.maccabipedia.co.il"

_BUCKET_LABELS = {
    Bucket.EXACT: "התאמה ודאית",
    Bucket.AMBIGUOUS: "דורש הכרעה",
    Bucket.UNMATCHED: "ללא התאמה",
    Bucket.ALREADY_PRESENT: "כבר קיים בדף",
    Bucket.OVERFLOW: "אין מקום פנוי",
}

_STYLE = """
:root{--blue:#0a2a66;--yellow:#ffe000;--line:#e3e6eb;--bg:#f6f7f9;--card:#fff;--muted:#5b6470}
*{box-sizing:border-box}
body{margin:0;padding:18px;background:var(--bg);color:#1b1f24;
     font:15px/1.5 "Segoe UI",Arial,sans-serif}
.wrap{max-width:1100px;margin:0 auto}
h1{color:var(--blue);margin:0 0 4px;font-size:1.5rem}
.sub{color:var(--muted);margin:0 0 18px;font-size:.9rem}
.counts{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 20px;padding:0;list-style:none}
.counts li{background:var(--card);border:1px solid var(--line);border-radius:10px;
           padding:9px 14px;min-width:130px}
.counts .n{display:block;font-size:1.35rem;font-weight:700;color:var(--blue)}
.counts .k{font-size:.8rem;color:var(--muted)}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;
        margin:0 0 11px;padding:10px 14px}
summary{cursor:pointer;font-weight:600;color:var(--blue)}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:.87rem}
th,td{text-align:right;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;white-space:nowrap}
a{color:var(--blue)}
.b-exact{border-right:4px solid #1a7f37}
.b-ambiguous{border-right:4px solid #bf8700}
.b-unmatched{border-right:4px solid #b35900}
.b-already_present,.b-overflow{border-right:4px solid var(--line)}
.tag{display:inline-block;padding:1px 7px;border-radius:20px;background:#eef1f6;
     font-size:.76rem;color:var(--muted);white-space:nowrap}
.score{font-variant-numeric:tabular-nums;white-space:nowrap}
"""


def wiki_url(page_name: str) -> str:
    """Maccabipedia serves articles on a bare path."""
    return f"{WIKI_BASE_URL}/{page_name.replace(' ', '_')}"


def _escape(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def _page_link(page_name: str) -> str:
    return f'<a href="{_escape(wiki_url(page_name))}" target="_blank">{_escape(page_name)}</a>'


def _target_cell(match: VideoMatch) -> str:
    if match.page_name:
        return _page_link(match.page_name)
    if match.candidates:
        return "<br>".join(_page_link(candidate) for candidate in match.candidates)
    return "—"


def _match_row(match: VideoMatch) -> str:
    parsed = match.parsed
    score = (f"{parsed.maccabi_points}:{parsed.opponent_points}" if parsed else "—")
    opponent = parsed.opponent_raw if parsed else "—"
    kind = match.kind.value if match.kind else "—"
    return (
        f'<tr class="b-{match.bucket.value}">'
        f'<td><a href="{_escape(match.url)}" target="_blank">{_escape(match.entry.title)}</a></td>'
        f'<td><span class="tag">{_escape(match.source)}</span></td>'
        f'<td><span class="tag">{_escape(kind)}</span></td>'
        f'<td class="score">{_escape(score)}</td>'
        f"<td>{_escape(opponent)}</td>"
        f'<td><span class="tag">{_escape(_BUCKET_LABELS.get(match.bucket, match.bucket.value))}</span></td>'
        f"<td>{_escape(match.reason)}</td>"
        f"<td>{_target_cell(match)}</td>"
        f"<td>{_escape(match.slot or '—')}</td>"
        f"</tr>"
    )


def _season_section(season: str, matches: list[VideoMatch]) -> str:
    counts = Counter(match.bucket for match in matches)
    summary_bits = ", ".join(
        f"{_BUCKET_LABELS.get(bucket, bucket.value)}: {count}"
        for bucket, count in sorted(counts.items(), key=lambda item: item[0].value)
    )
    rows = "\n".join(_match_row(match) for match in matches)
    return (
        f"<details><summary>{_escape(season or 'ללא עונה')} — {len(matches)} סרטונים "
        f"({_escape(summary_bits)})</summary>"
        "<table><thead><tr>"
        "<th>סרטון</th><th>ערוץ</th><th>סוג</th><th>תוצאה</th><th>יריבה</th>"
        "<th>סטטוס</th><th>סיבה</th><th>דף המשחק</th><th>פרמטר</th>"
        "</tr></thead><tbody>"
        f"{rows}"
        "</tbody></table></details>"
    )


def _counts_list(matches: list[VideoMatch], skipped_non_game: int) -> str:
    counts = Counter(match.bucket for match in matches)
    items = [
        f'<li><span class="n">{counts.get(bucket, 0)}</span>'
        f'<span class="k">{_escape(label)} ({bucket.value})</span></li>'
        for bucket, label in _BUCKET_LABELS.items()
    ]
    items.append(f'<li><span class="n">{len(matches)}</span>'
                 f'<span class="k">סרטוני משחק שנבדקו</span></li>')
    items.append(f'<li><span class="n">{skipped_non_game}</span>'
                 f'<span class="k">סרטונים שאינם משחק</span></li>')
    return f'<ul class="counts">{"".join(items)}</ul>'


def _sort_key(season: str) -> str:
    return season or "0000/00"


def render_report(matches: list[VideoMatch], skipped_non_game: int,
                  sample_section: str = "") -> str:
    """The full review page. `sample_section` is the verification sample, added later."""
    by_season: dict[str, list[VideoMatch]] = defaultdict(list)
    for match in matches:
        by_season[match.entry.season].append(match)

    sections = "\n".join(
        _season_section(season, sorted(by_season[season], key=lambda match: match.bucket.value))
        for season in sorted(by_season, key=_sort_key, reverse=True)
    )
    writable = sum(1 for match in matches if match.bucket == Bucket.EXACT and match.slot)

    return (
        "<!doctype html>"
        '<html lang="he" dir="rtl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>סרטוני משחקי כדורסל — דוח התאמה</title>"
        f"<style>{_STYLE}</style></head><body><div class=\"wrap\">"
        "<h1>סרטוני משחקי כדורסל — דוח התאמה</h1>"
        f'<p class="sub">נוצר ב-{date.today().strftime("%d-%m-%Y")} · '
        f"{writable} סרטונים מוכנים לכתיבה לדפי המשחקים · "
        "שום דבר עדיין לא נכתב לוויקי</p>"
        f"{_counts_list(matches, skipped_non_game)}"
        f"{sample_section}"
        f"{sections}"
        "</div></body></html>"
    )
