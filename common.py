"""공통 스키마, 저장소, 중복 제거, 키워드 필터."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "items.json"


def load_config(path: Path | None = None) -> dict:
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class Item:
    """모든 수집기가 돌려주는 공통 형식."""
    source: str                 # pubmed / unikorea / rss
    source_name: str            # 사람이 읽는 출처 이름 (예: NK News)
    title: str
    url: str
    published: str = ""         # YYYY-MM-DD
    summary: str = ""           # 초록·요약 원문 (사이트에는 그대로 싣지 않음)
    authors: str = ""
    venue: str = ""             # 학술지명 등
    lang: str = ""
    ids: dict = field(default_factory=dict)  # pmid, doi 등
    # 판정 결과
    keyword_hit: bool = False
    score: int | None = None
    category: str = ""
    summary_ko: str = ""
    reason: str = ""
    collected_at: str = ""

    @property
    def key(self) -> str:
        """중복 제거 키: DOI > PMID > 정규화 URL > 제목."""
        if self.ids.get("doi"):
            return "doi:" + self.ids["doi"].lower()
        if self.ids.get("pmid"):
            return "pmid:" + str(self.ids["pmid"])
        if self.url:
            u = re.sub(r"[?#].*$", "", self.url.strip().lower()).rstrip("/")
            return "url:" + hashlib.sha1(u.encode()).hexdigest()[:16]
        t = re.sub(r"\W+", "", self.title.lower())
        return "title:" + hashlib.sha1(t.encode()).hexdigest()[:16]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


# ---------------- 저장소 (JSON 파일, Git에서 변경 내역 추적 가능) ----------------

def load_store(path: Path = DATA_FILE) -> dict[str, dict]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {d["key"]: d for d in json.load(f)}


def save_store(store: dict[str, dict], path: Path = DATA_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(store.values(), key=lambda d: (d.get("published") or "", d["key"]), reverse=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)


def item_to_record(item: Item) -> dict:
    d = asdict(item)
    d["key"] = item.key
    return d


SEEN_FILE = ROOT / "data" / "seen.json"


def load_seen(path: Path = SEEN_FILE) -> set[str]:
    """키워드 필터에서 탈락한 항목의 키 (다음 실행 때 다시 처리하지 않도록)."""
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return set(json.load(f))


def save_seen(seen: set[str], path: Path = SEEN_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=0)


def merge_new(store: dict[str, dict], items: list[Item], rejected: set[str] | None = None) -> list[Item]:
    """저장소·탈락목록에 없는 항목만 돌려줌 (배치 내 중복도 제거)."""
    seen = set(store) | (rejected or set())
    fresh = []
    for it in items:
        if it.key in seen:
            continue
        seen.add(it.key)
        fresh.append(it)
    return fresh


# ---------------- 1차 키워드 필터 ----------------

def keyword_match(item: Item, kw: dict) -> bool:
    text = f"{item.title} {item.summary}".lower()
    nk = any(k.lower() in text for k in kw["north_korea"])
    oral = any(k.lower() in text for k in kw["oral"])
    return nk and oral
