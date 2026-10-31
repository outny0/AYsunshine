# AY션샤인 팀 대시보드

사회인 야구팀 AY션샤인의 모바일 대시보드. 두 리그 사이트 경기기록을 스크래핑해 `data.json`을 만들고, 단일 페이지 `index.html`이 읽어서 보여준다.
- 사이트: https://outny0.github.io/AYsunshine/ (GitHub Pages, main 브랜치에 push하면 1~2분 뒤 반영)
- 사용자: 팀 운영자. 한국어로, 짧고 쉽게 설명. 핸드폰(Claude 앱 Code)이나 PC에서 작업함.

## 파일
| 파일 | 역할 |
|------|------|
| `index.html` | 모바일 SPA (vanilla JS, 해시 라우팅 `#/` `#/games` `#/game/<id>` `#/week` `#/lineup/<id>` `#/players` `#/player/<이름>`). 선수 탭 '리그 순위' = `data.json` `awards` |
| `data.json` | 올 시즌 전체 + `years`·`history`(연도별 팀/선수 기록). **Actions가 자동 커밋하므로 직접 고칠 일 거의 없음** |
| `seasons/YYYY.json` | 지난 시즌(2019~2025) 박스스코어·집계. 한 번 받아두면 끝 (`--archive`) |
| `scrape_leagues.py` | 정왕+안양 수집 → `data_scraped.json` |
| `validate_scrape.py` | 리그 사이트 시즌 누적과 대조, 불일치 시 exit 1 |
| `.github/workflows/update.yml` | 매주 월 03:00 / 수 21:00 KST 자동 수집→검증→data.json 커밋 (수동: Actions → update-data → Run workflow) |
| `laptop_update.ps1` | 노트북 예약 작업 `AY션샤인_안양갱신`(월 07:00 / 수 22:00, 놓치면 켜진 뒤): pull → 안양 포함 수집 → 검증 → data.json 커밋·push. 로그 `%LOCALAPPDATA%\AYsunshine\logs\` |
| `apps_script/Code.gs` | 출석 투표·라인업 저장소 (Google Apps Script 웹 앱 + 구글 시트). 설치법 `apps_script/설치_안내.md` |
| `records/` | 전체 기록 보관본: `AY션샤인_전체기록.xlsx`(시트 8개) + 같은 내용 CSV. `export_records.py`로 생성 (엑셀 수기 원본은 삭제함, 이게 대체) |
| `docs/` | 개발기록(스크래퍼 함정 상세), 작업일지 |

## 실행
```bash
PYTHONIOENCODING=utf-8 python scrape_leagues.py          # 올해 시즌 (종료 경기는 cache/ 재사용)
PYTHONIOENCODING=utf-8 python validate_scrape.py         # 검증
cp data_scraped.json data.json                           # 검증 통과 시에만
python scrape_leagues.py --archive 2019-2025             # 지난 시즌 다시 받기 (필요할 때만)
python export_records.py                                 # records/ 보관본 다시 만들기 (기록 갱신 후 가끔, openpyxl 필요: pip install openpyxl)
python -m http.server 8765                               # 로컬 확인 → http://localhost:8765/
```
- 표준 라이브러리만 사용 (pip 설치 불필요)
- 리그 서버 배려: 요청 간격 1.5초, 종료 경기는 캐시. 같은 페이지 반복 요청 금지 (shbaseball robots.txt Crawl-delay 86400)

## 데이터 출처와 함정 (상세: docs/AY션샤인_대시보드_개발기록.md "리그 스크래퍼")
- 정왕 = shbaseball.co.kr (UTF-8, 팀번호 294). 일정 검색·기록지는 **PC URL** 사용 (모바일 POST는 빈 페이지). 검증용 시즌 누적은 모바일 UA로.
- 안양 = alb.or.kr (cp949). 오래된 SSL → SECLEVEL=1, 깨진 `P3P :` 헤더 때문에 청크 직접 해제(`dechunk`). 리그 시즌 ≠ 달력 연도(`league_season`).
- 한 칸에 타석 여러 개(`4구 4구`) → 공백·쉼표 분리, 주루 이벤트는 앞 타석에 붙임. `스낫(출)`은 삼진 아님. `=4회콜드` 같은 메모는 타석 아님.
- 안양은 투수 세부 기록이 빈 경기 있음(`pitch_complete=false`) → ERA 과소. 기권승·몰수승은 `forfeit`.
- 개인 순위(`awards`): 정왕 PC 기록실 `/record/getPlayerRecordList.hs` POST, 부문마다 정렬된 첫 페이지(30명)만 → 부문당 1회 요청. 규정 적용 파라미터가 타자 `applyRagulationPlate`, 투수 `applyRagulationInnings`로 다름. ERA는 7이닝 기준(우리 집계와 같음). 안양은 해외 접속 차단이라 아직 없음 (노트북에서는 접속됨, 2026-10-31)
- 화면의 연도 = 경기 날짜 기준. 엑셀 시절 FY = 안양 리그 시즌 기준 + 시장기·PO 제외.

## 작업 규칙
- 변경 후 브라우저로 화면 확인, 콘솔 오류 없는지 확인하고 push
- 스크래퍼를 고치면 `validate_scrape.py` 통과 확인
- 작업은 이 저장소에서만 한다 (2026-10-26 사용자 PC·OneDrive 사본은 삭제함, 업로드 스크립트도 없음). 반영은 git push로.
- `data_scraped.json`, `cache/`는 커밋하지 않음 (.gitignore)
- 작업이 끝나면 `docs/작업일지_YYMMDD.md`에 한 일 기록

## 진행 상황 / 남은 일
- 출석 투표·라인업: **연결 완료 (2026-10-26)**. Apps Script 프로젝트 `AY 선샤인 대시보드`(outny0@gmail.com, script.google.com/home), 데이터는 드라이브 시트 `AY션샤인 참석·라인업`. `Code.gs`를 고치면 배포 관리 → 새 버전으로 재배포(URL 유지). 새 프로젝트 직후엔 `401 invalid_client`(OAuth client not fully created) — 10분쯤 기다리면 풀림
- 팀 로고(`팀로고.png`) 헤더·파비콘 적용 완료
- 선택: 다음 경기 일정 자동 수집(안양은 공지글 형태라 어려움)
