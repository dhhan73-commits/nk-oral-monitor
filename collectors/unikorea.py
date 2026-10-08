"""통일부 북한정보포털 수집기 — 공공데이터포털(data.go.kr) 오픈API.

공공데이터포털 API는 응답 필드명이 서비스마다 다릅니다. 그래서
  1) 응답 JSON 안에서 '항목 목록'을 자동으로 찾고
  2) 제목·링크·날짜 필드를 후보 이름으로 추정합니다.
추정이 틀리면 config.yaml의 서비스 항목에 field_map을 넣어 고정하세요.
  예) field_map: {title: nttSj, url: detailUrl, date: pstgYmd, summary: cn}
처음 실행 시 응답의 필드명 목록을 로그로 출력하므로 그걸 보고 정하면 됩니다.
"""
from __future__ import annotations

import itertools
import os
import re
from datetime import date, timedelta

import requests

from common import Item, strip_html

CANDIDATES = {
    "title": ["title", "ttl", "sj", "nttSj", "subject", "titl", "kornm", "nm", "dataNm"],
    "url": ["url", "link", "detailUrl", "linkUrl", "dtlUrl", "pageUrl"],
    "date": ["pstgYmd", "regDt", "regYmd", "pblcnYmd", "pubDate", "date", "ymd", "frstRegDt", "wrtYmd"],
    "summary": ["cn", "content", "contents", "summary", "smry", "dc", "description", "abstract"],
}


def find_records(obj) -> list[dict]:
    """JSON 트리에서 dict로 이루어진 가장 긴 리스트를 찾는다."""
    best: list[dict] = []

    def walk(o):
        nonlocal best
        if isinstance(o, list):
            if o and all(isinstance(x, dict) for x in o) and len(o) > len(best):
                best = o
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            # data.go.kr 흔한 형태: items: {item: {...}} (항목이 1개일 때 dict)
            if "item" in o and isinstance(o["item"], dict) and not best:
                best = [o["item"]]
            for v in o.values():
                walk(v)

    walk(obj)
    return best


def _pick(rec: dict, field: str, field_map: dict) -> str:
    if field in field_map:
        return str(rec.get(field_map[field]) or "")
    lower = {k.lower(): k for k in rec}
    for cand in CANDIDATES[field]:
        if cand.lower() in lower and rec[lower[cand.lower()]]:
            return str(rec[lower[cand.lower()]])
    return ""


def _norm_date(s: str) -> str:
    digits = re.sub(r"\D", "", s)[:8]
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return s[:10]


def to_items(payload: dict, service_name: str, field_map: dict | None = None) -> list[Item]:
    field_map = field_map or {}
    out = []
    for rec in find_records(payload):
        title = strip_html(_pick(rec, "title", field_map))
        if not title:
            continue
        out.append(Item(
            source="unikorea",
            source_name=f"통일부 {service_name}",
            title=title,
            url=_pick(rec, "url", field_map) or "https://nkinfo.unikorea.go.kr",
            published=_norm_date(_pick(rec, "date", field_map)),
            summary=strip_html(_pick(rec, "summary", field_map))[:2000],
            lang="ko",
        ))
    return out


def collect(cfg: dict, lookback_days: int, log=print) -> list[Item]:
    c = cfg["unikorea"]
    key = os.getenv("DATA_GO_KR_KEY")
    if not key:
        log("[unikorea] DATA_GO_KR_KEY 미설정 → 건너뜀")
        return []
    bgng = (date.today() - timedelta(days=lookback_days)).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")
    items: list[Item] = []
    for svc in c["services"]:
        if not svc.get("endpoint"):
            log(f"[unikorea] '{svc['name']}' endpoint 미설정 → 건너뜀")
            continue
        extra = svc.get("extra_params") or {}
        # extra_params의 값이 리스트인 항목은 전부 조합해서 돈다 (예: cl x thema)
        combo_keys = list(extra.keys())
        combo_values = [extra[k] if isinstance(extra[k], list) else [extra[k]] for k in combo_keys]
        combos = list(itertools.product(*combo_values)) if combo_keys else [()]
        for kw in svc.get("search_keywords", [""]):
            for combo in combos:
                params = {
                    "serviceKey": key, "pageNo": 1, "numOfRows": c.get("num_of_rows", 100),
                    "keyword": kw, "bgng_ymd": bgng, "end_ymd": end,
                    "returnType": "json", "type": "json", "_type": "json",
                }
                params.update(dict(zip(combo_keys, combo)))
                try:
                    r = requests.get(svc["endpoint"], params=params, timeout=30)
                    r.raise_for_status()
                    payload = r.json()
                except Exception as e:  # 한 호출 실패가 전체를 멈추지 않도록
                    log(f"[unikorea] {svc['name']} '{kw}' {combo} 실패: {e}")
                    continue
                recs = find_records(payload)
                if recs:
                    log(f"[unikorea] {svc['name']} '{kw}' {combo}: {len(recs)}건, 필드={sorted(recs[0].keys())}")
                items += to_items(payload, svc["name"], svc.get("field_map"))
    return items
