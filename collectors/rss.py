"""RSS 수집기 — feedparser."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import feedparser

from common import Item, strip_html

UA = "nk-oral-monitor/0.1 (+research; SNU School of Dentistry)"


def _date(entry) -> str:
    for k in ("published_parsed", "updated_parsed"):
        t = entry.get(k)
        if t:
            return time.strftime("%Y-%m-%d", t)
    return ""


def parse_feed(feed_src, feed_name: str, lookback_days: int) -> list[Item]:
    """feed_src: URL 또는 RSS 문자열/파일 경로 (테스트용)."""
    parsed = feedparser.parse(feed_src, agent=UA)
    if not parsed.entries and parsed.get("bozo"):
        # feedparser는 네트워크 오류도 예외 없이 빈 결과로 돌려주므로 직접 올린다
        raise RuntimeError(f"피드를 읽지 못함: {parsed.get('bozo_exception')}")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    items = []
    for e in parsed.entries:
        pub = _date(e)
        if pub and pub < cutoff:
            continue
        items.append(Item(
            source="rss",
            source_name=feed_name,
            title=strip_html(e.get("title", "")),
            url=e.get("link", ""),
            published=pub,
            summary=strip_html(e.get("summary", ""))[:2000],
        ))
    return items


def collect(cfg: dict, lookback_days: int, log=print) -> list[Item]:
    items = []
    for f in cfg["rss"]["feeds"]:
        try:
            got = parse_feed(f["url"], f["name"], lookback_days)
            log(f"[rss] {f['name']}: {len(got)}건")
            items += got
        except Exception as e:
            log(f"[rss] {f['name']} 실패: {e}")
    return items
