# ⚾ AY션샤인 야구 대시보드 — 전체 개발 기록

> 최종 업데이트: 2026-06-12  
> GitHub Pages: https://outny0.github.io/AYsunshine/  
> GitHub Repo: https://github.com/outny0/AYsunshine  
> Google Sheets ID: `19Uc_jjR0trSLlsxQuqVxt9Z2Y6svE-0m34Hq_Pk5cig`

---

## 📁 폴더 구조

```
★개인작업★/선샤인대시보드/
├── index.html                    ← 대시보드 본체 (GitHub Pages에 올라가는 파일)
├── data.json                     ← 파싱된 데이터 (index.html이 읽는 파일)
├── make_data_json.py             ← xlsx → data.json 변환 스크립트
├── push_to_github_sunshine.py    ← GitHub 자동 업로드 스크립트
├── 업데이트.bat                  ← ★ 클릭 한 번으로 파싱+업로드 자동화
├── AY선샤인 Sabermetrics.xlsx    ← 구글 시트에서 내려받은 원본 데이터
├── 팀로고.png
└── AY션샤인_대시보드_개발기록.md  ← 이 파일
```

---

## 🔄 업데이트 워크플로

**매 경기 후 데이터 업데이트 순서:**

1. 구글 시트에 경기 데이터 붙여넣기 (기존과 동일)
2. 구글 시트 → **파일 → 다운로드 → Microsoft Excel(.xlsx)** → `선샤인대시보드` 폴더에 저장 (기존 파일 덮어쓰기)
3. **`업데이트.bat` 더블클릭** → 파싱 + GitHub 업로드 자동 완료
4. https://outny0.github.io/AYsunshine/ 에서 확인

> **수동 방법:** `make_data_json.py` → `push_to_github_sunshine.py` 순서대로 더블클릭  
> **Python 없으면?** → https://www.python.org 에서 설치 (openpyxl은 make_data_json.py가 자동 설치)

### 업데이트.bat 동작 방식
```bat
echo. | python make_data_json.py    ← input() 자동 넘김, 오류 시 exit code 1 반환
if %errorlevel% neq 0 → 중단 (파싱 실패 시 GitHub 업로드 막음)
python push_to_github_sunshine.py   ← 업로드 완료 후 Enter 대기
```

---

## 🏗️ 아키텍처 변천사

### Phase 1: Cowork 아티팩트 (현재 사용 안 함)
- Cowork에서 `window.cowork.callMcpTool()`로 Google Drive MCP 호출
- 구글 시트를 마크다운 테이블로 변환 → JS에서 직접 파싱
- **문제**: Cowork 환경 전용 API → GitHub Pages 등 외부에서 작동 안 함

### Phase 2: GitHub Pages + 직접 fetch (실패)
- Google Sheets CSV export URL로 직접 fetch 시도
- **문제**: CORS 차단 (외부 도메인에서 Google export URL 접근 불가)
- gviz/tq 엔드포인트로 교체 시도했지만 불안정

### Phase 3: 현재 방식 ✅ (xlsx → data.json → GitHub Pages)
- 구글 시트를 xlsx로 내려받기 → Python(openpyxl)으로 직접 파싱
- 깔끔한 `data.json` 생성 → GitHub에 index.html + data.json 업로드
- **장점**: CORS 완전 해결, 파싱 안정적, 오프라인에서도 최신 데이터 확인 가능

---

## 📊 data.json 구조

```json
{
  "updated": "2026-06-12 12:09",
  "games": [
    {"date": "02.21 (토)", "year": "2026", "league": "정왕", "opp": "엔젤스",
     "scored": 10, "allowed": 9, "result": "승"}
  ],
  "batters": [
    {"name": "전성열", "pa": 35, "ab": 34, "h": 15, "rbi": 19, "r": 1, "sb": 2, "avg": 0.441}
  ],
  "pitchers": [
    {"name": "김형종", "g": 6, "ip": 27.0, "h": 44, "bb": 8, "so": 16,
     "r": 53, "er": 44, "era": 11.41, "w": 2, "l": 4, "s": 0}
  ],
  "jw_batters": [...],    // 정왕 탭용
  "jw_pitchers": [...],   // 정왕 탭용
  "ay_batters": [...],    // 안양 탭용
  "ay_pitchers": [...],   // 안양 탭용
  "past_ay_games": [      // 안양 과거 경기 (2019~2025, 74경기)
    {"date": "11.15", "year": "2025", "league": "안양", "opp": "경기블루오션",
     "result": "승", "scored": 13, "allowed": 10}
  ],
  "jw_seasons": [         // 정왕 시즌별 요약 (2020~2026, 8시즌)
    {"year": "2025", "league_name": "정왕주말리그", "g": 14, "w": 11, "l": 3, "d": 0, "rs": 166, "ra": 96}
  ],
  "past_batters": [       // FY22~FY25 선수별 연도별 기록 (81건)
    {"name": "전성열", "year": "FY25", "pa": 15, "ab": 11, "h": 2, "rbi": 0, "r": 1, "sb": 1, "avg": 0.182}
  ]
}
```

---

## 🧮 make_data_json.py 파싱 로직

### 읽는 시트

| 시트명 | 용도 |
|--------|------|
| FY26 정왕(상세기록) | 2026 정왕 경기별 상세기록 (타자+투수+점수) |
| FY26 안양(상세기록) | 2026 안양 경기별 상세기록 |
| 안양이전경기기록 | 안양 전체 게임 히스토리 (2019~2025) |
| 정왕이전경기기록 | 정왕 시즌별 요약 (2020~2026) |
| FY25 정왕 | FY25 정왕 선수 기록 |
| FY25 안양 | FY25 안양 선수 기록 (AY션샤인 필터) |
| FY24 정왕 | FY24 선수 기록 |
| FY24 안양 | FY24 선수 기록 |
| FY23 정왕 | FY23 선수 기록 |
| FY23 안양 | FY23 선수 기록 |
| FY22 정왕 | FY22 선수 기록 |
| FY22 안양 | FY22 선수 기록 |

### FY22~FY25 시트 헤더 위치 차이

| 시트 | 헤더 위치 | 비고 |
|------|-----------|------|
| FY25 정왕 | row 1 (row 0이 빈 줄) | `find_hdr(rows, ['순위','선수명'])` 로 자동 탐지 |
| FY24~FY22 정왕 | row 0 | 동일 함수로 처리 |
| 모든 연도 안양 | row 1 (row 0이 `-` 구분선) | `find_hdr(rows, ['PLAYERS','R.'])` |

### 정왕 상세기록 컬럼 구조 (xlsx 기준, 1-indexed)

**점수 테이블:**
- B열(idx1): "스코어" → 게임 시작 감지
- J열(idx9): R(총득점)
- ⚠️ AY가 선공이면 순서 반대 → `c(ra,1)=='AY션샤인'` 체크로 판별

**AY 타자 섹션:**
- B열(idx1): "AY션샤인", K열(idx10): "타석" → 섹션 헤더
- 데이터: K=타석(10), L=타수(11), M=안타(12), N=타점(13), O=득점(14), P=도루(15)

**AY 투수 섹션:**
- B열(idx1): "AY션샤인", D열(idx3): "등판" → 섹션 헤더
- 데이터: F=이닝(5), J=피안타(9), L=4사구(11), M=삼진(12), N=실점(13), O=자책(14)

### 안양 상세기록 컬럼 구조

**게임 감지:**
- C열(idx2): "VS", D열(idx3): "AY션샤인" → 게임 시작
- L열(idx11): R(총득점) — 게임 +3행/+4행

**AY 타자 섹션:**
- B열(idx1): "AY션샤인", L열(idx11): "타석" → 섹션 헤더
- 데이터: N=타석(13), O=타수(14), P=득점(15), Q=안타(16), R=타점(17)

**투수 섹션:**
- B열(idx1): "팀", C열(idx2): "선수" → 헤더
- AY 행 필터: `'AY' in team or '션샤인' in team`
- 데이터: F=이닝(5), I=피안타(8), K=4구(10), L=사구(11), M=삼진(12), N=실점(13), O=자책(14)

### FY25~FY22 정왕 컬럼 인덱스 (0-based)
```
col0=순위, col1=선수명, col2=타율, col4=타석(pa), col5=타수(ab),
col6=안타(h), col11=타점(rbi), col12=득점(r), col13=도루(sb)
```

### FY25~FY22 안양 컬럼 인덱스 (0-based)
```
col1=PLAYERS(이름), col2=TEAMS(팀), col5=AVG,
col9=TPA(pa), col10=AB(ab), col11=HIT(h),
col19=RBI(rbi), col20=RUN(r), col21=SB(sb)
```
필터: `'AY' in col2 or '션샤인' in col2`, 구분선 행(`col1 == '-'`) 스킵

### 이닝 누적 방법 (야구 표기법)
```python
def ip_to_outs(ip):
    # 4.1이닝 = 4이닝 1아웃 = 13아웃
    full = int(ip)
    partial = round((float(ip) - full) * 10)  # .1 → 1, .2 → 2
    return full * 3 + partial

def outs_to_ip(outs):
    return float(f"{outs//3}.{outs%3}")
```

### ERA 계산 (사회인 야구 7이닝 기준)
```python
era = round(er * 7 / ip_dec, 2)  # ip_dec = outs/3
```

---

## 🎨 index.html UI 구조 (현재 버전)

### 전체 레이아웃 (탭 없는 단일 스크롤 페이지)

```
┌─────────────────────────────┐
│  ⚾ AY션샤인  FY26  [↻]     │ ← sticky 헤더
│  RS/G │ RA/G │ RD │ AVG │ERA │ ← 팀 통계 스트립
│  통합  │  정왕 │  안양        │ ← 리그 탭
├─────────────────────────────┤
│  최근 경기 폼 도트           │
├─────────────────────────────┤
│  🏏 타자 기록                │
│  [타율▼][안타][타점][득점]...│ ← 정렬 칩
│  # │이름│AVG │H │RBI│SB     │ ← 컴팩트 테이블
│  AVG 색상: ≥.350=초록, <.250=빨강 │
├─────────────────────────────┤
│  ⚡ 투수 기록                │
│  [ERA▼][WHIP][K/BB][이닝]   │
│  # │이름│ERA │W-L│K │BB     │
│  ERA 색상: ≤5=초록, ≥9=빨강  │
├─────────────────────────────┤
│  📅 경기 기록                │
│  ▼ 2026 시즌 [기본 열림]    │
│  ▶ 정왕 역대 시즌 [기본 닫힘]│ ← 시즌 요약 테이블
│  ▶ 안양 2025 [기본 닫힘]    │ ← 경기별 목록
│  ▶ 안양 2024 [기본 닫힘]    │
│  ...                         │
└─────────────────────────────┘
```

---

## 🔑 JavaScript 핵심 함수 구조

```javascript
loadData()
  → fetch('data.json')
  → buildData(json)          // JSON → 내부 data 구조로 변환
  → data = { all, jw, ay }  // 리그별 분리
  → renderAll()

switchLeague(l):
  curLeague = l
  renderAll()   // 전체 리렌더

rebuildBatters(batters):
  // #bat-tbl 업데이트
  // #bat-sb .chip on 클래스 업데이트  ← 버그 수정 포인트
  // #qbtn 업데이트

toggleAccordion(id):
  // 아코디언 상태: accordionState[id] = true/false
```

---

## 🐛 버그 수정 이력

### [2026-06-12] parse_all_past_batters 함수 누락으로 데이터 업데이트 불가
- **현상**: 업데이트.bat 실행 시 겉보기엔 성공하지만 data.json이 실제로 갱신 안 됨
- **원인**: `make_data_json.py`에서 `parse_all_past_batters(wb)` 호출하지만 함수 미정의 → NameError 발생 → except 블록에서 잡혀 종료 코드 0으로 반환 → 오류 있어도 push 진행
- **수정**:
  1. `find_hdr(rows, keys)` 함수 추가 — 헤더 행 위치 자동 탐지 (시트마다 헤더가 다른 행에 있음)
  2. `parse_all_past_batters(wb)` 함수 추가 — FY22~FY25 전 시트 순회하여 타자 기록 수집
  3. except 블록에 `sys.exit(1)` 추가 — 오류 시 배치 파일이 감지하고 중단

### [2026-05-29] 정렬 칩 색상 안 바뀌는 문제
- **원인**: `sort-chips` div가 `#bat-tbl` 외부에 있어 `rebuildBatters` 재렌더 시 칩 갱신 안 됨
- **수정**: `id="bat-sb"/"pit-sb"`, `data-key` 추가 + `rebuildBatters` 끝에 칩 `on` 클래스 동기화

### [2026-05-29] 선공/후공 경기 점수 반전
- **원인**: AY가 선공일 때 스코어 행 순서가 반대 (i+2=AY, i+3=상대)
- **수정**: `c(ra,1)=='AY션샤인'` 체크로 행 순서 판별

### [2026-05-29] 업데이트.bat 한글 인코딩 오류
- **원인**: bat 파일을 UTF-8로 저장했으나 Windows cmd는 CP949로 읽음 → 한글 echo가 명령어로 오인식
- **수정**: bat 파일 echo 문구를 영어(ASCII)로 교체, CRLF 줄 끝으로 저장

---

## 📱 GitHub Pages 설정

### 활성화 방법
1. GitHub repo → Settings → Pages
2. Source: Deploy from a branch
3. Branch: main → / (root)
4. Save

### push_to_github_sunshine.py
```python
TOKEN = "(토큰은 PC의 push_to_github_sunshine.py 참고)"  # 만료 시 재발급 필요
REPO  = "outny0/AYsunshine"
ALWAYS = ["index.html", "data.json"]  # 매번 업로드
ONCE   = [".nojekyll"]                # 최초 1회만
```

**토큰 만료 시 재발급:**
GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
→ Generate new token (classic) → repo 체크 → 생성 후 `push_to_github_sunshine.py` TOKEN 값 교체

---

## 📈 현재 데이터 현황 (2026-06-12 기준)

| 항목 | 내용 |
|------|------|
| FY26 정왕 | 12경기 (7승 5패) |
| FY26 안양 | 1경기 (0승 1패) |
| 과거 안양 | 74경기 (2019~2025) |
| 정왕 역대 | 8시즌 요약 (2020~2026) |
| FY26 타자 | 16명 |
| FY26 투수 | 7명 |
| 과거 타자 기록 | 81건 (FY22~FY25, 27명) |

---

## 🕷️ 리그 스크래퍼 (2026-10-22 추가, Phase 4 준비)

엑셀 수동 입력 대신 두 리그 사이트에서 경기 기록을 직접 읽어옴. 아직 `data.json`을 대체하지 않고 `data_scraped.json`으로 따로 출력.

```
python scrape_leagues.py           # 올해 시즌 → data_scraped.json (종료 경기는 cache/ 재사용)
python scrape_leagues.py --refresh # 캐시 무시
python validate_scrape.py          # 리그 사이트 시즌 누적 + 기존 data.json 과 대조
```

| 리그 | 사이트 | 경기 목록 | 경기 기록 |
|------|--------|-----------|-----------|
| 정왕 | shbaseball.co.kr (UTF-8) | PC `/schedule/getGameSchedule.hs` POST, `searchGameTeamSeq=294` (모바일 POST는 빈 페이지) | PC `/schedule/getGameRecord.hs?gameScheduleSeq=N` |
| 안양 | alb.or.kr (cp949) | `/z/zboard.php?id=game&category=2(토요)/1(일요)&x=on&y=on&keyword=AY션샤인` | `/z/view.php?id=game&no=N` |

**함정 정리**
- 정왕 이닝 칸 하나에 타석이 둘일 수 있음: `4구 4구`, `4구,도루,4구,주자아웃` → 공백·쉼표로 나누고 도루·폭투·포일·견제 등 이벤트는 앞 타석에 붙임
- 정왕 사이트는 `스낫(출)`(낫아웃 출루)을 삼진으로 안 셈 → 맞춤
- 안양 서버: 오래된 DH 키 → `SECLEVEL=1` SSL 컨텍스트 필요 / `P3P : ...` 깨진 헤더 때문에 urllib이 chunked 본문을 못 풀어 `1f5f` 같은 값이 섞임 → `dechunk()`로 직접 해제
- 안양 시즌 누적 페이지는 주소에 `order=` 없으면 SQL 오류, 데이터 행이 머리행보다 한 칸 짧음
- 안양 리그 시즌 ≠ 달력 연도 (2026-04-11 경기는 '2025년' 시즌) → `league_season` 필드로 보관
- 안양 투수 세부 기록이 비는 경기 있음(2026-10-10) → 투수 1명이면 이닝·피안타·실점·승패를 박스스코어로 보정, 삼진·볼넷·자책은 0으로 남음 (`pitch_complete: false`)
- robots.txt: 정왕 `Crawl-delay: 86400` → 요청 간격 1.5초 + 종료 경기 캐시, 주 1~2회 실행

**검증 결과 (2026 시즌, 2026-10-22)**: 19경기(정왕 14 / 안양 5). 정왕 타자 17명·투수 7명, 안양(연합회장기) 타자 14명 → 사이트 시즌 누적과 전 항목 일치. 엑셀 13경기 점수 전부 일치, 6/12까지 타자 기록 전원 일치. 투수 승리 1건만 엑셀(김형종)과 사이트(이우진)가 다름 → 사이트 기준.

### 전환 완료 (2026-10-22)
- `업데이트.bat` = 수집 → 검증(불일치 시 중단) → `data_scraped.json`을 `data.json`으로 복사 → GitHub 업로드. 예전 엑셀 방식은 `업데이트_엑셀방식.bat`, 엑셀 시절 data는 `data_엑셀백업.json`
- `index.html` = 모바일 5화면(홈/경기/박스스코어/선수/선수상세, 해시 라우팅 `#/game/<id>`, `#/player/<이름>`). 예전 화면은 `index_엑셀방식.html`
- 새 index.html 은 `data.json`의 `box`·`stats` 필드가 필요 (엑셀 버전 data.json 으로는 안 뜸)
- GitHub Actions `.github/workflows/update.yml`: 월 03:00 / 수 21:00 KST 자동 수집·커밋. 저장소에는 `scrape_leagues.py`, `validate_scrape.py`만 올림 (**push 스크립트는 토큰 때문에 올리지 않음**). 워크플로 파일은 토큰에 `workflow` 권한이 없어 API 업로드가 404 → 웹에서 직접 추가 필요

### 자동 갱신 = GitHub Actions(정왕) + 노트북(안양) (2026-10-25 확정)
- **GitHub Actions `update-data`** — 월 03:00 · 수 21:00 KST, 켜져 있음. 10/25 21:44 시험 실행 성공·커밋 확인
  - **안양(alb.or.kr)은 해외 접속을 막는다.** 시험 결과: 기본 DNS 에서 이름 못 찾음 → 주소(115.68.112.27)를 직접 줘도 연결 시간 초과. (구글 DNS 는 SERVFAIL, Cloudflare 는 응답 — 한국에선 정상)
  - 그래서 Actions 는 `SKIP_ALB=1` — 정왕·정왕 일정만 새로 받고, 안양 경기·안양 예정은 지난 data.json 값 유지(예정은 오늘 이후만). `ay_live:false`·`ay_updated`=지난 수집 시각. 검증은 안양 대조 생략
  - 화면: 안양 수집일이 전체 갱신일과 다르면 머리에 「안양 M.D 기준」
- 토큰에 `workflow` 권한 추가(10/25, 사용자 휴대폰) — 이제 `.github/workflows/` 도 push 스크립트로 올라감
- 안양 새 기록은 **노트북**이 채운다 — 작업 스케줄러 **「AY션샤인_대시보드_주간갱신」** — 월 03:00 · 수 21:00, 꺼져 있었으면 켜질 때 실행(StartWhenAvailable), 30분 제한
  - 실행 `%LOCALAPPDATA%\ay_sunshine\run_update.ps1`(UTF-8 BOM): 수집 → 검증(불일치면 중단, 업로드 안 함) → data.json 교체 → data.json 만 업로드
  - 로그 `%LOCALAPPDATA%\ay_sunshine\logs\update_YYMMDD_HHMM.log` · 10/25 21:33 시험 실행 exit 0
  - 노트북 전용(사무실 PC 는 11/2부터 GitHub 차단). index.html·스크립트를 고치면 업로드는 따로
- 토큰 권한: `repo, workflow`

### 예정 경기 (2026-10-25 추가)
- `scrape_leagues.py` → `data.json` 의 `upcoming` (오늘 이후 경기, 날짜·시간순). 한 리그가 실패해도 다른 리그는 살리고 경고만 남김
- 안양: `/s/schedule/s3.php?gyear=&limit=300` 전체 경기일정 표 `['10/31/11:30(석)', 1루팀, 3루팀, 리/토/플/기]` — **연도가 없다** → 오늘 기준으로 붙임(지금보다 6달 넘게 앞선 달이면 내년). 구장 `석`=석수, 나머지는 약자 그대로(`박` 등)
- 정왕: 같은 일정 검색에서 `경기종료` 아닌 행. **10/25 현재 정왕 2026 일정에 남은 경기가 없어 실제 행으로는 시험 못 함** — 지난 경기 행으로 팀·구장 파싱만 확인. 다음 시즌 첫 일정이 올라오면 한 번 확인할 것
- 화면: 홈 맨 위 「다음 경기」 카드(D-day, 뒤 3경기 목록) · 경기 탭 맨 위 「예정」 묶음. 지난 시즌 화면·해당 리그 예정 없으면 안 보임. 화면에서도 오늘 이전 경기는 한 번 더 거름(수집 뒤 며칠 지나도 지난 경기가 남지 않게)
- ⚠ GitHub Actions 로 돌릴 거면 저장소의 `scrape_leagues.py` 도 새 판으로 올려야 `upcoming` 이 생긴다 → 10/25 21:2x data.json·index.html·scrape_leagues.py 3개 배포, 라이브 확인(upcoming 2건). 토큰 보관 위치는 사용자 결정으로 그대로 둠

---

## 💡 다음 개선 아이디어

- [ ] 투수 FY22~FY25 과거 기록 추가 (현재 타자만)
- [ ] 2루타/3루타/홈런 컬럼 추가 → OBP/SLG/OPS 계산 가능
- [ ] 팀 득실차 누적 그래프 (경기수 x축, 누적 RD y축)
- [ ] 선수별 시즌 트렌드 모달 (타율 추이)
- [ ] 앱 아이콘/PWA 설정으로 홈 화면 추가 가능하게

---

> 💡 **핵심 교훈:**  
> xlsx → Python 파싱 → data.json → GitHub Pages 구조가 가장 안정적.  
> 브라우저에서 실시간 파싱하면 CORS, 인증, 포맷 변환 문제가 계속 생김.  
> 파싱은 Python에서 한 번 확실하게, 브라우저는 표시만.
