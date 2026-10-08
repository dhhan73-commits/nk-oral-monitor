"""PubMed 수집기 — NCBI E-utilities (esearch → efetch XML)."""
from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import requests

from common import Item

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _params(extra: dict) -> dict:
    p = {"db": "pubmed", "tool": "nk-oral-monitor"}
    if os.getenv("NCBI_EMAIL"):
        p["email"] = os.environ["NCBI_EMAIL"]
    if os.getenv("NCBI_API_KEY"):
        p["api_key"] = os.environ["NCBI_API_KEY"]
    p.update(extra)
    return p


def search_ids(query: str, lookback_days: int, retmax: int) -> list[str]:
    """최근 lookback_days 동안 PubMed에 등록(entrez date)된 PMID 목록."""
    mindate = (date.today() - timedelta(days=lookback_days)).strftime("%Y/%m/%d")
    maxdate = date.today().strftime("%Y/%m/%d")
    r = requests.get(f"{BASE}/esearch.fcgi", params=_params({
        "term": query, "retmode": "json", "retmax": retmax,
        "datetype": "edat", "mindate": mindate, "maxdate": maxdate,
    }), timeout=30)
    r.raise_for_status()
    return r.json()["esearchresult"]["idlist"]


def fetch_xml(pmids: list[str]) -> str:
    time.sleep(0.4)  # 키 없이 초당 3회 제한 준수
    r = requests.get(f"{BASE}/efetch.fcgi", params=_params({
        "id": ",".join(pmids), "retmode": "xml"}), timeout=60)
    r.raise_for_status()
    return r.text


def _text(el) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def _pubdate(art) -> str:
    """ArticleDate(전자출판일) 우선, 없으면 JournalIssue PubDate."""
    for path in ("ArticleDate", "Journal/JournalIssue/PubDate"):
        d = art.find(path)
        if d is None:
            continue
        y = _text(d.find("Year"))
        if not y:
            continue
        m = _text(d.find("Month")) or "1"
        m = MONTHS.get(m[:3], m)
        dd = _text(d.find("Day")) or "1"
        try:
            return f"{int(y):04d}-{int(m):02d}-{int(dd):02d}"
        except ValueError:
            return f"{y}-01-01"
    return ""


def parse_xml(xml_text: str) -> list[Item]:
    root = ET.fromstring(xml_text)
    items = []
    for pa in root.findall("PubmedArticle"):
        mc = pa.find("MedlineCitation")
        art = mc.find("Article")
        pmid = _text(mc.find("PMID"))
        abstract = " ".join(_text(a) for a in art.findall("Abstract/AbstractText"))
        authors = []
        for au in art.findall("AuthorList/Author"):
            last, ini = _text(au.find("LastName")), _text(au.find("Initials"))
            if last:
                authors.append(f"{last} {ini}".strip())
        doi = ""
        for aid in pa.findall("PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = _text(aid)
        authors_str = ", ".join(authors[:3]) + (" 외" if len(authors) > 3 else "")
        items.append(Item(
            source="pubmed",
            source_name="PubMed",
            title=_text(art.find("ArticleTitle")),
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            published=_pubdate(art),
            summary=abstract,
            authors=authors_str,
            venue=_text(art.find("Journal/Title")),
            lang=_text(art.find("Language")),
            ids={"pmid": pmid, "doi": doi},
        ))
    return items


def collect(cfg: dict, lookback_days: int) -> list[Item]:
    c = cfg["pubmed"]
    ids = search_ids(c["query"], lookback_days, c.get("retmax", 100))
    if not ids:
        return []
    items = []
    for i in range(0, len(ids), 50):
        items += parse_xml(fetch_xml(ids[i:i + 50]))
    return items
