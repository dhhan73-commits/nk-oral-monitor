"""매일 실행: 수집 → 중복 제거 → 판정 → 저장 → 사이트 생성.

사용법
  python run.py                 # 전체 실행
  python run.py --no-classify   # Claude 판정 없이 수집만
  python run.py --only rss      # 특정 수집기만 (pubmed, unikorea, rss)
"""
from __future__ import annotations

import argparse

from classify import classify
from collectors import pubmed, rss, unikorea
from common import (Item, item_to_record, load_config, load_seen, load_store,
                    merge_new, now_iso, save_seen, save_store)
from build_site import build

COLLECTORS = {
    "pubmed": lambda cfg, d: pubmed.collect(cfg, d),
    "unikorea": lambda cfg, d: unikorea.collect(cfg, d),
    "rss": lambda cfg, d: rss.collect(cfg, d),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-classify", action="store_true")
    ap.add_argument("--only", choices=list(COLLECTORS))
    args = ap.parse_args()

    cfg = load_config()
    if args.no_classify:
        cfg["classifier"]["enabled"] = False
    days = cfg.get("lookback_days", 7)
    store = load_store()
    rejected = load_seen()

    # 1) 수집
    collected: list[Item] = []
    for name, fn in COLLECTORS.items():
        if args.only and name != args.only:
            continue
        if not cfg.get(name, {}).get("enabled", True):
            continue
        try:
            got = fn(cfg, days)
            print(f"[{name}] 수집 {len(got)}건")
            collected += got
        except Exception as e:
            print(f"[{name}] 수집기 오류: {e}")

    # 2) 중복 제거
    fresh = merge_new(store, collected, rejected)
    print(f"[run] 신규 {len(fresh)}건 (전체 수집 {len(collected)}건)")

    # 3) 이전 실행에서 판정 못 한 항목도 재시도
    pending = [Item(**{k: v for k, v in r.items() if k != "key"})
               for r in store.values() if r.get("keyword_hit") and r.get("score") is None]
    if pending:
        print(f"[run] 판정 대기 재시도 {len(pending)}건")

    stamp = now_iso()
    for it in fresh:
        it.collected_at = stamp
    classify(fresh + pending, cfg)

    # 4) 저장 — 키워드 통과 항목만 보관 (무관 기사로 저장소가 커지지 않도록)
    for it in fresh + pending:
        if it.keyword_hit:
            store[it.key] = item_to_record(it)
        else:
            rejected.add(it.key)
    save_store(store)
    save_seen(rejected)

    # 5) 사이트 생성
    n = build(cfg, store)
    print(f"[run] 사이트 생성 완료: 게시 {n}건")


if __name__ == "__main__":
    main()
