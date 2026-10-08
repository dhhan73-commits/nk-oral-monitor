# 북한 구강보건 자료 모니터 (프로토타입)

PubMed, 통일부 북한정보포털 오픈API, RSS에서 북한 치과·구강보건 자료를 매일 모으고,
Claude로 관련성을 판정해 GitHub Pages 정적 사이트로 게시합니다.

```
수집 (pubmed / unikorea / rss)
  → 중복 제거 (DOI > PMID > URL > 제목)
  → 1차 키워드 필터 ('북한' 단어 AND '구강' 단어, 북한식 표기 포함)
  → 2차 Claude 판정 (관련도 1~5점, 분류, 한국어 요약)
  → data/items.json 저장
  → docs/index.html 생성 (min_score 이상만 게시)
```

## 파일 구성

| 파일 | 역할 |
|---|---|
| `config.yaml` | 검색어, RSS 목록, 판정 모델·기준 점수 등 모든 설정 |
| `collectors/pubmed.py` | NCBI E-utilities 수집기 |
| `collectors/unikorea.py` | 공공데이터포털(통일부) 수집기 |
| `collectors/rss.py` | RSS 수집기 |
| `classify.py` | 키워드 필터 + Claude 판정 |
| `build_site.py` | 정적 사이트 생성 |
| `run.py` | 전체 실행 |
| `tests/` | 네트워크·키 없이 도는 테스트 (가짜 Claude 사용) |
| `.github/workflows/daily.yml` | 매일 한국시간 06:17 자동 실행 |

## 설치 (GitHub)

1. GitHub에 새 저장소(비공개 가능)를 만들고 이 폴더 전체를 올립니다.
2. **Settings → Secrets and variables → Actions**에서 아래 Secret을 등록합니다.

   | 이름 | 필수 | 받는 곳 |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | 판정에 필수 | console.anthropic.com |
   | `DATA_GO_KR_KEY` | 북한정보포털 수집에 필수 | 공공데이터포털 활용신청 후 마이페이지 → 일반 인증키(**Decoding**) |
   | `NCBI_EMAIL` | 권장 | 본인 연락 이메일 |
   | `NCBI_API_KEY` | 선택 | NCBI 계정 설정 (초당 요청 한도 3→10회) |

3. **Settings → Pages**에서 Source를 `Deploy from a branch`, 브랜치 `main`, 폴더 `/docs`로 지정합니다.
4. **Actions → daily-collect → Run workflow**로 첫 실행을 해 봅니다.

비공개 저장소의 Pages 공개 여부는 GitHub 요금제에 따라 다릅니다. 내부용으로만 쓰려면 Pages를 끄고 `docs/index.html`을 내려받아 열어도 됩니다.

## 북한정보포털 API 연결 (한 번만)

공공데이터포털 상세 페이지는 자동으로 읽을 수 없어 엔드포인트를 비워 두었습니다.

1. data.go.kr에서 「통일부_북한정보포털 통합검색 서비스」, 「통일부_북한 동향 조회 서비스」를 활용신청합니다 (개발계정 자동승인).
2. 상세 페이지의 **서비스URL**과 오퍼레이션 경로를 이어 붙인 주소를 `config.yaml`의 `unikorea.services[].endpoint`에 넣습니다.
3. 수동 실행 후 Actions 로그에서 `필드=[...]` 줄을 확인합니다. 제목·날짜가 비어 나오면 그 필드명으로 `field_map`을 지정합니다.
   ```yaml
   field_map: {title: nttSj, url: detailUrl, date: pstgYmd, summary: cn}
   ```

## 로컬 실행

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v   # 오프라인 테스트
export ANTHROPIC_API_KEY=... DATA_GO_KR_KEY=...
python run.py                 # 전체
python run.py --only pubmed   # 수집기 하나만
python run.py --no-classify   # Claude 없이 (모두 3점 처리)
```

## 운영 메모

- **비용**: 키워드 필터를 통과한 신규 항목만 Claude에 보냅니다. 1회 상한은 `max_items_per_run`(기본 200건)입니다.
- **판정 실패·키 없음**: 점수 없이 저장되고 다음 실행 때 다시 판정합니다.
- **탈락 항목**: `data/seen.json`에 키만 남겨 다음 실행에서 다시 처리하지 않습니다.
- **게시 범위**: 사이트에는 제목·링크·출처·날짜와 Claude가 새로 쓴 요약만 싣습니다. 초록·기사 원문은 `data/`에만 남고 사이트에는 나가지 않습니다.
- **북한 매체**: 국내 접속이 차단된 북한 사이트(조선중앙통신, 로동신문 웹사이트 등)는 RSS 목록에 넣지 마십시오. 정보통신망법 개정 상황을 확인한 뒤 추가 여부를 정하는 것이 안전합니다.
- **판정 품질**: 처음 몇 주는 `data/items.json`의 `score`와 `reason`을 보고 `config.yaml`의 `min_score`나 `classify.py`의 판정 기준 문구를 조정하십시오.
