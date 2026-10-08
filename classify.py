"""2차 판정: Claude가 관련성 점수·분류·한국어 요약을 붙인다.

- 1차 키워드 필터를 통과한 항목만 Claude에 보낸다 (비용 절감).
- PubMed는 검색식 자체가 정밀하므로 키워드 필터를 건너뛰고 바로 판정.
- 응답은 tool 호출로 받아 JSON 형식을 강제한다.
"""
from __future__ import annotations

import os

from common import Item

CATEGORIES = [
    "연구논문",
    "북한 내 구강보건 정책·제도",
    "북한 내 구강보건 동향·보도",
    "북향민(탈북민) 구강건강",
    "국제협력·인도적 지원",
    "기타",
]

SYSTEM = (
    "당신은 북한 구강보건 자료를 선별하는 연구보조원입니다. "
    "서울대 치의학대학원 통일치의학협력센터가 운영하는 자료 모니터 사이트에 "
    "게시할 가치가 있는지 판단합니다. "
    "관련성 기준: 북한 주민 또는 북향민(탈북민)의 구강건강, 치과의료, 구강보건 정책·인력·"
    "시설·물자, 남북 또는 국제 치과 협력을 직접 다루면 높은 점수. "
    "북한 일반 보건의료 기사에서 치과가 한두 문장 언급되면 중간 점수. "
    "'이발'이 머리 깎기를 뜻하는 등 단어만 겹치는 경우는 1점. "
    "요약은 원문 문장을 옮기지 말고 당신의 말로 2~3문장 한국어로 쓰세요."
)

TOOL = {
    "name": "record_judgement",
    "description": "자료의 관련성 판정 결과를 기록한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5,
                      "description": "1=무관, 3=부분 관련, 5=핵심 자료"},
            "category": {"type": "string", "enum": CATEGORIES},
            "summary_ko": {"type": "string", "description": "자신의 말로 쓴 2~3문장 한국어 요약"},
            "reason": {"type": "string", "description": "점수 근거 한 문장"},
        },
        "required": ["score", "category", "summary_ko", "reason"],
    },
}


def build_prompt(it: Item) -> str:
    return (
        f"출처: {it.source_name}\n제목: {it.title}\n"
        f"저자/학술지: {it.authors} / {it.venue}\n날짜: {it.published}\n"
        f"내용 발췌:\n{it.summary[:3000] or '(본문 없음 — 제목만으로 판단)'}"
    )


def judge(client, model: str, it: Item) -> dict:
    msg = client.messages.create(
        model=model,
        max_tokens=600,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "record_judgement"},
        messages=[{"role": "user", "content": build_prompt(it)}],
    )
    for block in msg.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("tool_use 응답 없음")


def classify(items: list[Item], cfg: dict, client=None, log=print) -> list[Item]:
    c = cfg["classifier"]
    kw = cfg["keywords"]
    from common import keyword_match

    candidates = []
    for it in items:
        it.keyword_hit = it.source == "pubmed" or keyword_match(it, kw)
        if it.keyword_hit:
            candidates.append(it)
    log(f"[classify] 키워드 통과 {len(candidates)}/{len(items)}건")

    if not c.get("enabled", True):
        for it in candidates:
            it.score, it.category = 3, "기타"
        return items

    if client is None:
        if not os.getenv("ANTHROPIC_API_KEY"):
            log("[classify] ANTHROPIC_API_KEY 미설정 → 판정 보류(score 없음)")
            return items
        import anthropic
        client = anthropic.Anthropic()

    for it in candidates[: c.get("max_items_per_run", 200)]:
        try:
            j = judge(client, c["model"], it)
            it.score = int(j["score"])
            it.category = j["category"]
            it.summary_ko = j["summary_ko"].strip()
            it.reason = j["reason"].strip()
        except Exception as e:
            log(f"[classify] 판정 실패 ({it.title[:40]}): {e}")
    return items
