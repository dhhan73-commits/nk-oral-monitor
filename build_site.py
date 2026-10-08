"""data/items.json → docs/index.html (GitHub Pages용 정적 페이지) + docs/items.json.

사이트에는 제목·링크·출처·날짜와 Claude가 새로 쓴 한국어 요약만 싣고,
수집한 초록·기사 원문은 싣지 않는다 (저작권·북한 매체 재유통 문제 방지).
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from common import ROOT, load_config, load_store, now_iso

PUBLIC_FIELDS = ["title", "url", "source", "source_name", "published", "authors",
                 "venue", "category", "score", "summary_ko"]

TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600&family=Noto+Sans+KR:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{{--bg:#f6f4ef;--card:#fff;--ink:#1d2329;--muted:#66707a;--line:#e3dfd6;--accent:#1f5f74;--chip:#e8f0f2}}
@media (prefers-color-scheme:dark){{:root{{--bg:#14181c;--card:#1c2228;--ink:#e6e9ec;--muted:#9aa4ad;--line:#2c343b;--accent:#7fc0d4;--chip:#21323a}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 "Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif}}
header{{max-width:880px;margin:0 auto;padding:40px 16px 8px}}
h1{{font-family:"Noto Serif KR",serif;font-size:28px;margin:0 0 4px;letter-spacing:-.01em}}
.sub{{color:var(--muted);margin:0}}
.meta{{color:var(--muted);font-size:13px;margin-top:6px}}
.controls{{max-width:880px;margin:16px auto;padding:0 16px;display:flex;gap:8px;flex-wrap:wrap}}
input,select{{font:inherit;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}}
input{{flex:1 1 240px}}
main{{max-width:880px;margin:0 auto;padding:0 16px 60px}}
article{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:10px 0}}
article h2{{font-size:16px;margin:0 0 6px;line-height:1.45}}
article h2 a{{color:var(--ink);text-decoration:none}}
article h2 a:hover{{color:var(--accent);text-decoration:underline}}
.row{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:13px;color:var(--muted)}}
.chip{{background:var(--chip);color:var(--accent);border-radius:999px;padding:1px 10px;font-weight:600}}
.stars{{color:var(--accent);letter-spacing:1px}}
p.sum{{margin:8px 0 0}}
.empty{{color:var(--muted);text-align:center;padding:40px 0}}
footer{{max-width:880px;margin:0 auto;padding:0 16px 40px;color:var(--muted);font-size:12px}}
</style></head><body>
<header><h1>{title}</h1><p class="sub">{subtitle}</p>
<p class="meta">게시 {count}건 · 마지막 갱신 {updated} (UTC)</p></header>
<div class="controls">
<input id="q" type="search" placeholder="제목·요약 검색 (예: 구강과, 불소, 북향민)">
<select id="cat"><option value="">전체 분류</option>{cat_options}</select>
<select id="src"><option value="">전체 출처</option>{src_options}</select>
</div>
<main id="list">{cards}</main>
<p class="empty" id="none" hidden>조건에 맞는 자료가 없습니다.</p>
<footer>제목·링크와 자동 생성 요약만 제공하며 원문은 각 출처에서 확인하십시오. 요약은 Claude가 작성한 것으로 오류가 있을 수 있습니다.</footer>
<script>
const q=document.getElementById('q'),cat=document.getElementById('cat'),src=document.getElementById('src');
const cards=[...document.querySelectorAll('article')],none=document.getElementById('none');
function f(){{const t=q.value.trim().toLowerCase();let n=0;
for(const c of cards){{const ok=(!t||c.dataset.text.includes(t))&&(!cat.value||c.dataset.cat===cat.value)&&(!src.value||c.dataset.src===src.value);
c.hidden=!ok;if(ok)n++;}}none.hidden=n>0;}}
[q,cat,src].forEach(e=>e.addEventListener('input',f));
</script></body></html>
"""


def _card(d: dict) -> str:
    e = html.escape
    stars = "●" * (d.get("score") or 0) + "○" * (5 - (d.get("score") or 0))
    byline = " · ".join(x for x in [d.get("authors"), d.get("venue")] if x)
    text = f"{d['title']} {d.get('summary_ko', '')} {byline}".lower()
    return (
        f'<article data-cat="{e(d.get("category", ""))}" data-src="{e(d["source_name"])}" '
        f'data-text="{e(text)}">'
        f'<h2><a href="{e(d["url"])}" target="_blank" rel="noopener">{e(d["title"])}</a></h2>'
        f'<div class="row"><span class="chip">{e(d.get("category") or "미분류")}</span>'
        f'<span>{e(d["source_name"])}</span><span>{e(d.get("published") or "")}</span>'
        f'<span class="stars" title="관련도 {d.get("score")}/5">{stars}</span></div>'
        + (f'<div class="row">{e(byline)}</div>' if byline else "")
        + (f'<p class="sum">{e(d["summary_ko"])}</p>' if d.get("summary_ko") else "")
        + "</article>"
    )


def build(cfg: dict, store: dict[str, dict]) -> int:
    site = cfg["site"]
    min_score = cfg["classifier"].get("min_score", 3)
    rows = [d for d in store.values() if (d.get("score") or 0) >= min_score]
    rows.sort(key=lambda d: (d.get("published") or "", d.get("score") or 0), reverse=True)

    def opts(values):
        return "".join(f'<option>{html.escape(v)}</option>' for v in sorted({v for v in values if v}))

    out_dir = ROOT / site.get("output_dir", "docs")
    out_dir.mkdir(parents=True, exist_ok=True)
    page = TEMPLATE.format(
        title=html.escape(site["title"]), subtitle=html.escape(site.get("subtitle", "")),
        count=len(rows), updated=now_iso().replace("T", " ").rstrip("Z"),
        cat_options=opts(d.get("category") for d in rows),
        src_options=opts(d["source_name"] for d in rows),
        cards="".join(_card(d) for d in rows) or '<p class="empty">아직 게시된 자료가 없습니다.</p>',
    )
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    (out_dir / "items.json").write_text(
        json.dumps([{k: d.get(k) for k in PUBLIC_FIELDS} for d in rows], ensure_ascii=False, indent=1),
        encoding="utf-8")
    (out_dir / ".nojekyll").touch()
    return len(rows)


if __name__ == "__main__":
    c = load_config()
    print(build(c, load_store()))
