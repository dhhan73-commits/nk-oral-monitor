# CLAUDE.md — 북한 구강보건 자료 모니터

이 파일은 Claude Code가 이 프로젝트를 이어받을 때 읽는 작업 메모입니다.

## 목적
북한 치과·구강보건 자료를 매일 자동 수집·선별해 웹사이트로 제공한다.
운영 주체: 서울대 치의학대학원 통일치의학협력센터 (한동헌 교수).
사용자와의 대화·주석·커밋 메시지는 한국어로 한다.

## 현재 상태 (2026-10-08, claude.ai에서 프로토타입 작성)
- 파이프라인: 수집(pubmed/unikorea/rss) → 중복 제거 → 키워드 필터 → Claude 판정 → `data/items.json` → `docs/index.html`
- 오프라인 테스트 8개 통과: `python -m unittest discover -s tests -v`
- **실제 네트워크 호출은 아직 한 번도 검증하지 못함** (작성 환경에서 외부 접속 차단). 첫 작업은 실제 실행으로 각 수집기를 확인하는 것.
- 북한정보포털 API `endpoint`는 비어 있음. 공공데이터포털 활용신청 후 사용자가 서비스URL을 알려주면 `config.yaml`에 넣는다.

## 다음 할 일 (우선순위 순)
0. **먼저**: 루트의 `daily.yml.move-to-github-workflows`를 `.github/workflows/daily.yml`로 옮긴다 (원격 전송 시 `.github` 폴더에 직접 쓸 수 없어 루트에 둠). 그다음 `git init` 하고 첫 커밋.
1. `pip install -r requirements.txt` 후 `python run.py --only pubmed --no-classify`, `--only rss`로 실제 수집 확인. PubMed 검색식이 너무 넓거나 좁지 않은지 결과 건수와 제목을 사용자와 검토.
2. RSS 피드 URL이 살아 있는지 확인. 죽은 피드는 교체 (NK News, Daily NK, 38 North, Google 뉴스 검색 2개).
3. 북한정보포털 endpoint 연결 → 로그의 `필드=[...]`를 보고 필요하면 `field_map` 지정.
4. `ANTHROPIC_API_KEY`로 판정 실행 → `data/items.json`의 score·reason을 보며 `classify.py`의 SYSTEM 문구와 `min_score` 조정.
5. GitHub 저장소 생성, Secrets 등록(ANTHROPIC_API_KEY, DATA_GO_KR_KEY, NCBI_EMAIL, NCBI_API_KEY), Pages(/docs) 설정, workflow 수동 실행.
6. 이후 확장 후보: KCI·RISS·OpenAlex 수집기, 빅카인즈 뉴스 API(신청 필요), WHO GHO 구강보건 지표(월 1회), 로동신문 지면 등 수작업 입력 폼.

## 지켜야 할 원칙
- **북한 매체 사이트(조선중앙통신, 로동신문 웹 등)는 수집 대상에 넣지 않는다.** 국내에서 접속 차단 상태이며, 공개 사이트 재게시는 '유통' 문제가 될 수 있다. 정보통신망법 개정 여부를 사용자가 확인하기 전까지 유지.
- 사이트에는 제목·링크·출처·날짜·Claude가 새로 쓴 요약만 싣는다. 초록·기사 원문은 `data/`에만 둔다 (`build_site.PUBLIC_FIELDS`).
- 키워드 사전에는 북한식 표기(구강과, 삭은이, 이몸, 이솔, 이닦이약)를 유지. '이발'은 머리 깎기와 겹치므로 판정 단계에서 걸러지는지 계속 확인.
- 판정 모델 기본값 `claude-haiku-5-5`, 품질 우선 시 `claude-sonnet-5-5`.
- API 키는 코드·커밋에 넣지 말고 환경변수/GitHub Secrets로만.

## 구조
| 파일 | 역할 |
|---|---|
| `config.yaml` | 검색어, 피드, 판정 기준 등 모든 설정 |
| `common.py` | Item 스키마, 저장소(items.json, seen.json), 중복 키, 키워드 필터 |
| `collectors/*.py` | 수집기. 각 모듈은 `collect(cfg, lookback_days) -> list[Item]` |
| `classify.py` | 키워드 필터 + Claude tool 호출로 JSON 판정 |
| `build_site.py` | 정적 HTML·공개 JSON 생성 |
| `run.py` | 전체 실행 (`--only`, `--no-classify`) |
| `tests/` | 픽스처와 가짜 Claude로 도는 오프라인 테스트 |
| `.github/workflows/daily.yml` | 매일 UTC 21:17 (KST 06:17) 실행 후 data/docs 커밋 |

새 수집기를 추가할 때는 `collectors/`에 모듈을 만들고 `run.py`의 `COLLECTORS`와 `config.yaml`에 등록한 뒤, 픽스처 기반 테스트를 함께 추가한다.
