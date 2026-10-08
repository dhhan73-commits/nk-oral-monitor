"""네트워크·API 키 없이 돌아가는 테스트. GitHub Actions에서 수집 전에 실행된다."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FX = ROOT / "tests" / "fixtures"

from build_site import build  # noqa: E402
from classify import classify  # noqa: E402
from collectors import pubmed, rss, unikorea  # noqa: E402
from common import (Item, item_to_record, keyword_match, load_config,  # noqa: E402
                    load_seen, load_store, merge_new, save_seen, save_store)

FAR = 100000  # 고정 날짜 픽스처가 시간이 지나도 걸러지지 않도록


class FakeClient:
    """Claude API 대역: 제목에 '이발'이 있으면 1점, 아니면 4점."""

    def __init__(self):
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls += 1
        prompt = kw["messages"][0]["content"]
        score = 1 if "이발" in prompt else 4
        block = SimpleNamespace(type="tool_use", input={
            "score": score, "category": "북한 내 구강보건 동향·보도",
            "summary_ko": "시험 요약입니다.", "reason": "시험"})
        return SimpleNamespace(content=[block])


class TestCollectors(unittest.TestCase):
    def test_pubmed_parse(self):
        items = pubmed.parse_xml((FX / "pubmed.xml").read_text())
        self.assertEqual(len(items), 2)
        a, b = items
        self.assertIn("North Korean", a.title)          # 중첩 태그(<i>) 텍스트 보존
        self.assertEqual(a.published, "2026-09-21")      # ArticleDate 우선
        self.assertEqual(a.authors, "Kim A, Lee B, Park C 외")
        self.assertEqual(a.ids["doi"], "10.0000/TEST.1")
        self.assertEqual(b.published, "2025-12-03")      # PubDate 월 이름 변환
        self.assertEqual(b.summary, "")

    def test_unikorea_parse(self):
        payload = json.loads((FX / "unikorea.json").read_text())
        items = unikorea.to_items(payload, "통합검색")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].published, "2026-09-30")
        self.assertEqual(items[0].url, "https://nkinfo.unikorea.go.kr/test/1")
        self.assertNotIn("<p>", items[0].summary)

    def test_unikorea_single_item_and_field_map(self):
        payload = {"response": {"body": {"items": {"item": {"x": "제목A", "y": "2026.01.02"}}}}}
        items = unikorea.to_items(payload, "t", {"title": "x", "date": "y"})
        self.assertEqual([i.title for i in items], ["제목A"])
        self.assertEqual(items[0].published, "2026-01-02")

    def test_rss_parse(self):
        items = rss.parse_feed(str(FX / "feed.xml"), "Test", FAR)
        self.assertEqual(len(items), 4)
        self.assertEqual(items[0].published, "2026-10-05")


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()

    def test_dedupe_and_keywords(self):
        items = rss.parse_feed(str(FX / "feed.xml"), "Test", FAR)
        fresh = merge_new({}, items)
        self.assertEqual(len(fresh), 3)                  # 쿼리스트링만 다른 URL 중복 제거
        hits = [i.title for i in fresh if keyword_match(i, self.cfg["keywords"])]
        self.assertEqual(len(hits), 2)                   # 영문 치과 기사 + '이발' 오탐
        self.assertTrue(any("이발" in t for t in hits))

    def test_classify_filters_false_positive(self):
        items = (rss.parse_feed(str(FX / "feed.xml"), "Test", FAR)
                 + pubmed.parse_xml((FX / "pubmed.xml").read_text()))
        client = FakeClient()
        classify(merge_new({}, items), self.cfg, client=client, log=lambda *_: None)
        self.assertEqual(client.calls, 4)                # RSS 2 + PubMed 2 (주식 기사는 Claude에 안 보냄)

    def test_end_to_end_store_and_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cfg = dict(self.cfg, site=dict(self.cfg["site"], output_dir=str(tmp / "site")))
            items = merge_new({}, rss.parse_feed(str(FX / "feed.xml"), "Test", FAR)
                              + pubmed.parse_xml((FX / "pubmed.xml").read_text()))
            classify(items, cfg, client=FakeClient(), log=lambda *_: None)
            store = {i.key: item_to_record(i) for i in items if i.keyword_hit}
            save_store(store, tmp / "items.json")
            store2 = load_store(tmp / "items.json")
            self.assertEqual(len(store2), 4)
            n = build(cfg, store2)
            self.assertEqual(n, 3)                       # '이발' 기사(1점)는 게시 안 됨
            page = (tmp / "site" / "index.html").read_text()
            self.assertIn("Dental caries among North Korean", page)
            self.assertNotIn("이발관", page)
            self.assertNotIn("Synthetic abstract", page)  # 원문 초록은 싣지 않음
            # 재실행 시 신규 0건 (탈락 항목은 seen 목록으로 기억)
            rejected = {i.key for i in items if not i.keyword_hit}
            save_seen(rejected, tmp / "seen.json")
            again = merge_new(store2, rss.parse_feed(str(FX / "feed.xml"), "Test", FAR),
                              load_seen(tmp / "seen.json"))
            self.assertEqual(again, [])

    def test_no_api_key_leaves_pending(self):
        import os
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            items = pubmed.parse_xml((FX / "pubmed.xml").read_text())
            classify(items, self.cfg, log=lambda *_: None)
            self.assertTrue(all(i.keyword_hit and i.score is None for i in items))
        finally:
            if old:
                os.environ["ANTHROPIC_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()
