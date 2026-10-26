#!/usr/bin/env python3
"""AY션샤인 리그 스크래퍼  정왕(shbaseball.co.kr) + 안양(alb.or.kr) → data_scraped.json

사용법:
  python scrape_leagues.py              # 올해 시즌, 캐시된 경기는 다시 받지 않음
  python scrape_leagues.py --year 2026
  python scrape_leagues.py --refresh    # 경기 박스스코어 캐시 무시하고 전부 다시 받기
  python scrape_leagues.py --archive 2019-2025   # 지난 시즌 → seasons/YYYY.json (최초 1회)
"""
import sys, os, re, json, html, time, ssl, argparse
import urllib.request, urllib.parse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(SCRIPT_DIR, 'cache')
OUT_PATH   = os.path.join(SCRIPT_DIR, 'data_scraped.json')
BASE_JSON  = os.path.join(SCRIPT_DIR, 'data.json')   # 과거 기록(엑셀 기반)은 여기서 그대로 가져옴

TEAM      = 'AY션샤인'
JW_HOST   = 'https://www.shbaseball.co.kr'
JW_TEAM   = 294
ALB_HOST  = 'https://www.alb.or.kr'
UA        = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36'
UA_MOBILE = 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36'
DELAY     = 1.5   # 요청 간격(초) — 리그 서버 부담 줄이기

# --- HTTP ---
# alb.or.kr 서버가 오래된 DH 키를 써서 기본 보안수준(OpenSSL 3)에선 접속 거부됨 → 보안수준 1로 낮춘 컨텍스트
_ssl_legacy = ssl.create_default_context()
_ssl_legacy.set_ciphers('DEFAULT:@SECLEVEL=1')

_last = [0.0]
def fetch(url, data=None, enc='utf-8', referer=None, ua=UA):
    wait = DELAY - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={'User-Agent': ua})
    if referer: req.add_header('Referer', referer)
    ctx = _ssl_legacy if 'alb.or.kr' in url else None
    for attempt in range(3):          # 리그 서버가 가끔 응답 없음(시간 초과) → 쉬었다 재시도
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                raw = r.read()
                if not r.headers.get('Transfer-Encoding'): raw = dechunk(raw)
            break
        except OSError:
            if attempt == 2: raise
            time.sleep(10 * (attempt + 1))
    _last[0] = time.time()
    return raw.decode(enc, 'ignore')

def dechunk(raw):
    """alb.or.kr 은 'P3P : ...' 처럼 깨진 헤더를 보내 http.client 가 그 뒤 헤더(Transfer-Encoding: chunked)를
    못 읽음 → 본문에 청크 크기 줄이 그대로 섞여 들어옴. 청크 형식이면 직접 풀고, 아니면 그대로 반환"""
    if not re.match(rb'^[0-9a-fA-F]+\r\n', raw): return raw
    out, i = [], 0
    try:
        while True:
            j = raw.index(b'\r\n', i)
            size = int(raw[i:j], 16)
            if size == 0: return b''.join(out)
            out.append(raw[j+2:j+2+size])
            i = j + 2 + size + 2
    except ValueError:
        return raw

def cached(key, url, enc, refresh=False, **kw):
    """종료된 경기 페이지는 바뀌지 않으므로 cache/ 에 저장해두고 재사용"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, key + '.html')
    if not refresh and os.path.exists(path):
        with open(path, encoding='utf-8') as f: return f.read()
    t = fetch(url, enc=enc, **kw)
    with open(path, 'w', encoding='utf-8') as f: f.write(t)
    return t

# --- HTML 헬퍼 ---
def strip(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()

def tables(t):
    """페이지의 (여는태그, 행 목록) 리스트. 행은 셀 텍스트 리스트"""
    t = re.sub(r'(?s)<script.*?</script>|<style.*?</style>|<!--.*?-->', '', t)
    out = []
    for m in re.finditer(r'(?is)(<table[^>]*>)(.*?)</table>', t):
        rows = []
        for tr in re.findall(r'(?is)<tr.*?</tr>', m.group(2)):
            cs = [strip(c) for c in re.findall(r'(?is)<t[dh][^>]*>(.*?)</t[dh]>', tr)]
            if any(cs): rows.append(cs)
        out.append((m.group(1), rows))
    return out

def num(s):
    try: return float(str(s).replace(',', ''))
    except: return 0

def name_no(s):
    m = re.match(r'^(.*?)\s*\((\d+)\)\s*$', s.strip())
    return (m.group(1).strip(), m.group(2)) if m else (s.strip(), '')

def ip_to_outs(ip):
    """'4.1' → 13아웃, '6 ⅓' → 19아웃"""
    s = str(ip).replace('⅓', '.1').replace('⅔', '.2').replace(' ', '')
    if not s or s == '-': return 0
    full = int(num(s)); partial = round((num(s) - full) * 10)
    return full * 3 + partial

def outs_to_ip(outs):
    return float(f"{outs//3}.{outs%3}")

# --- 타석 결과 분류 ---
def pa_kind(t):
    """타석 결과 문자열 하나 → 'HR'|'3B'|'2B'|'1B'|'BB'|'HBP'|'SO'|'E'|'OUT'"""
    t = re.split(r'[,/]', t)[0].strip()
    if '홈' in t: return 'HR'
    if '사구' in t: return 'HBP'
    if '4구' in t or '고4' in t: return 'BB'
    if t == '스낫(출)': return 'E'     # 낫아웃 출루 — 리그 사이트가 삼진으로 안 세므로 맞춤
    if '삼진' in t or '스낫' in t: return 'SO'
    if '실' in t: return 'E'
    if re.search(r'[좌중우유][월선중]?3$|^[좌중우]3$|우중3|좌중3', t): return '3B'
    if re.search(r'[좌중우유][월선중]?2$|^[좌중우]2$|우중2|좌중2', t): return '2B'
    if '안' in t: return '1B'
    return 'OUT'

EVENT = re.compile(r'도루|폭투|주자아웃|보크|포구실|송구실|견제|주루사|포일')
def split_cells(cells):
    """정왕 이닝 칸들 → 타석 목록. 타자일순이면 '4구 4구', '4구,도루,4구,주자아웃'처럼 한 칸에 두 타석.
    공백·쉼표로 나누고 주루 이벤트(도루·폭투·포일 등)는 직전 타석에 붙임"""
    pas = []
    for cell in cells:
        for tok in re.split(r'[\s,]+', cell.strip()):
            if not tok or tok == '-': continue
            if EVENT.search(tok):
                if pas: pas[-1] += ',' + tok     # 칸 맨 앞 이벤트(대주자 도루·보크 등)는 타석이 아니므로 버림
            else: pas.append(tok)
    return pas

def add_pa_counts(b, pas):
    for k in ('d2', 'd3', 'hr', 'bb', 'hbp', 'so'): b.setdefault(k, 0)
    for p in pas:
        k = pa_kind(p)
        if k == '2B': b['d2'] += 1
        elif k == '3B': b['d3'] += 1
        elif k == 'HR': b['hr'] += 1
        elif k == 'BB': b['bb'] += 1
        elif k == 'HBP': b['hbp'] += 1
        elif k == 'SO': b['so'] += 1

# --- 정왕 ---
def jw_game_list(year):
    """PC 일정 검색(POST)으로 AY 경기 목록. 모바일 검색은 빈 페이지가 와서 PC 버전 사용"""
    url = JW_HOST + '/schedule/getGameSchedule.hs'
    t = fetch(url, referer=url, data={
        'num': 1, 'leagueCategory': 'NORMAL',
        'searchStartGameDate': f'{year}-01-01', 'searchEndGameDate': f'{year}-12-31',
        'searchYear': year, 'searchTopLeagueSeq': '00', 'searchLowerLeagueSeq': '00',
        'searchGameTeamSeq': JW_TEAM, 'searchStadiumSeq': '',
        'orderCondition': 'GAME_START_TIME', 'orderType': 'ASC', 'rowSize': 300})
    games, seen = [], set()
    for m in re.finditer(r'gameScheduleSeq=(\d+)', t):
        seq = m.group(1)
        if seq in seen: continue
        seen.add(seq)
        a = t.rfind('<tr', 0, m.start()); b = t.find('</tr>', m.start())
        row = strip(t[a:b])
        dm = re.search(r'(\d{2})\.(\d{2}) \((.)\) (\d{2}:\d{2})', row)
        lg = re.search(r'\d{2}:\d{2}\s+(.+?)\s+/\s+(\S+)', row)
        games.append({'seq': seq, 'done': '경기종료' in row,
                      'date': f'{year}-{dm.group(1)}-{dm.group(2)}' if dm else '',
                      'dow': dm.group(3) if dm else '', 'time': dm.group(4) if dm else '',
                      'comp': lg.group(1) if lg else '', 'div': lg.group(2) if lg else '', 'row': row})
    return games

def jw_upcoming(year, today):
    """정왕 일정 중 아직 안 끝난 경기. 행: '10.31 (토) 14:00 정왕주말리그 / 정왕토요4부 정왕야구장 AY션샤인 VS 상대 …'"""
    out = []
    for g in jw_game_list(year):
        if g['done'] or not g['date'] or g['date'] < today: continue
        m = re.search(r'/\s+\S+\s+(\S+)\s+(.+?)\s+VS\s+(.+?)(?:\s+(?:경기|우천|취소|연기|라인업|하이라이트)|$)', g['row'])
        if not m: continue
        clean = lambda s: re.sub(r'(?:^|\s)(?:콜드승|\d+)(?=\s|$)', ' ', s).strip()   # 점수·콜드 표시만 (팀명 속 숫자는 둔다)
        t1, t2 = clean(m.group(2)), clean(m.group(3))
        if TEAM not in (t1, t2): continue
        status = next((k for k in ('우천취소', '취소', '연기') if k in g['row']), '')
        out.append({'league': '정왕', 'date': g['date'], 'dow': g['dow'], 'time': g['time'],
                    'place': m.group(1), 'opp': t2 if t1 == TEAM else t1, 'home': t2 == TEAM,
                    'comp': g['comp'], 'div': g['div'], 'kind': '리그', 'status': status})
    return out

def jw_box(g, refresh=False):
    """PC 경기기록 페이지. 표 구성: scorebox / tb-info / player-score-box(장타·도루) / 타자×2 / 투수×2"""
    url = f"{JW_HOST}/schedule/getGameRecord.hs?gameScheduleSeq={g['seq']}&leagueCategory=NORMAL"
    t = cached(f"jw_{g['seq']}", url, 'utf-8', refresh)
    tb = tables(t)
    sc = next((rows for tag, rows in tb if 'scorebox' in tag and len(rows) >= 3), None)
    if not sc: raise ValueError(f"정왕 {g['seq']}: 스코어 표를 찾지 못함")
    teams = [sc[1][0], sc[2][0]]
    if TEAM not in teams: raise ValueError(f"정왕 {g['seq']}: {TEAM} 없음 {teams}")
    me = teams.index(TEAM); op = 1 - me
    def lrow(r):
        # [팀, 1~12회, R, H, E, B] — 진행 안 한 이닝은 '-'
        return {'inn': [x for x in r[1:-4] if x not in ('-', '')], 'r': int(num(r[-4])), 'h': int(num(r[-3])),
                'e': int(num(r[-2])), 'b': int(num(r[-1]))}
    ls = [lrow(sc[1]), lrow(sc[2])]

    batters, pitchers = [], []
    for tag, rows in tb:
        if not rows or rows[0][0] != TEAM: continue
        hdr = rows[0]
        if '타석' in hdr:
            # 행: [타순, 이름(번호), 포지션, 1~12회..., 타석 타수 안타 타점 득점 도루 타율]
            for r in rows[1:]:
                if not r[0].isdigit(): continue
                st = r[-7:]
                nm, no = name_no(r[1])
                pas = split_cells(r[3:-7])
                b = {'order': r[0], 'name': nm, 'no': no, 'pos': r[2], 'pas': pas,
                     'pa': int(num(st[0])), 'ab': int(num(st[1])), 'h': int(num(st[2])),
                     'rbi': int(num(st[3])), 'r': int(num(st[4])), 'sb': int(num(st[5]))}
                add_pa_counts(b, [p.split(',')[0] for p in pas])
                batters.append(b)
        elif '등판' in hdr:
            # 머리행 첫 칸(팀명)이 번호·이름 두 칸을 덮으므로 데이터는 +1 칸 밀림
            ix = {h: k + 1 for k, h in enumerate(hdr)}
            for r in rows[1:]:
                if not r[0].isdigit(): continue
                nm, no = name_no(r[1])
                pitchers.append({'name': nm, 'no': no, 'role': r[ix['등판']], 'dec': r[ix['결과']],
                                 'outs': ip_to_outs(r[ix['이닝']]), 'bf': int(num(r[ix['타자']])),
                                 'np': int(num(r[ix['투구수']])), 'h': int(num(r[ix['피안타']])),
                                 'hr': int(num(r[ix['홈런']])), 'bb': int(num(r[ix['4사구']])), 'hbp': 0,
                                 'so': int(num(r[ix['삼진']])), 'r': int(num(r[ix['실점']])),
                                 'er': int(num(r[ix['자책']]))})

    # 2루타/3루타/홈런은 장타 표 기준으로 덮어씀 (타석 문자열보다 정확)
    ev = next((rows for tag, rows in tb if 'player-score-box' in tag), None)
    if ev:
        col = ev[0].index(TEAM)
        for r in ev[1:]:
            if len(r) < 3: continue        # 심판·기록원 줄
            k = {'2루타': 'd2', '3루타': 'd3', '홈런': 'hr'}.get(r[1])
            if not k: continue
            cnt = {}
            for nm in re.findall(r'(\S+) \(\d+회\)', r[col]):
                cnt[nm] = cnt.get(nm, 0) + 1
            for b in batters: b[k] = cnt.get(b['name'], 0)

    return {'id': f"jw-{g['seq']}", 'league': '정왕', 'comp': g['comp'], 'div': g['div'],
            'date': g['date'], 'dow': g['dow'], 'time': g['time'],
            'opp': teams[op], 'home': me == 1,
            'scored': ls[me]['r'], 'allowed': ls[op]['r'], 'line': {'ay': ls[me], 'opp': ls[op]},
            'batters': batters, 'pitchers': pitchers, 'pitch_complete': True,
            'src': url}

# --- 안양 ---
def alb_game_list(year):
    """경기기록지 게시판을 팀명으로 검색. 경기 날짜 기준으로 해당 연도만"""
    kw = urllib.parse.quote(TEAM.encode('cp949'))
    games = []
    for cat in (2, 1):            # 2=토요, 1=일요
        page = 1
        while True:
            url = (f"{ALB_HOST}/z/zboard.php?id=game&page={page}&select_arrange=headnum&desc=asc&page_num=20"
                   f"&sn=off&ss=on&sc=off&category={cat}&x=on&y=on&keyword={kw}")
            t = fetch(url, enc='cp949')
            rows = re.findall(r"(?s)<FONT CLASS=list_scow>\d+</font>.*?(?=<FONT CLASS=list_scow>\d+</font>|경기목록)", t)
            if not rows: break
            older = False
            for r in rows:
                no = re.search(r'[?&]no=(\d+)', r)
                d = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})/\s*(\d{2}:\d{2})', strip(r))
                if not no or not d: continue
                y = int(d.group(1))
                if y < year: older = True; continue
                if y != year: continue
                games.append({'no': no.group(1), 'date': f"{y}-{int(d.group(2)):02d}-{int(d.group(3)):02d}",
                              'time': d.group(4), 'cat': '토요' if cat == 2 else '일요'})
            if older or f'page={page+1}&' not in t: break
            page += 1
    return games

DOW = '월화수목금토일'
ALB_PLACE = {'석': '석수'}
ALB_KIND = {'리': '리그', '토': '토너먼트', '플': '플레이오프', '기': '기타'}
def alb_upcoming(today):
    """전체 경기일정(s3.php) — 어제부터 앞으로의 경기. 행: ['10/31/11:30(석)', 1루팀, 3루팀, 비고(리/토/플/기)]
    연도가 없어서 오늘 기준으로 붙인다(지금이 11월인데 1월 경기면 내년)"""
    t = fetch(ALB_HOST + '/s/schedule/s3.php?gyear=&limit=300', enc='cp949')
    ty, tm = int(today[:4]), int(today[5:7])
    out = []
    for tag, rows in tables(t):
        for r in rows:
            if len(r) < 3 or TEAM not in r[1:3]: continue
            m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2}:\d{2})\(\s*(.*?)\s*\)', r[0])
            if not m: continue
            mo, d = int(m.group(1)), int(m.group(2))
            y = ty + 1 if mo < tm - 6 else ty
            date = f'{y}-{mo:02d}-{d:02d}'
            if date < today: continue
            opp = r[2] if r[1] == TEAM else r[1]
            out.append({'league': '안양', 'date': date, 'dow': DOW[datetime(y, mo, d).weekday()], 'time': m.group(3),
                        'place': ALB_PLACE.get(m.group(4), m.group(4)), 'opp': opp, 'home': r[1] == TEAM,
                        'comp': '', 'div': '', 'kind': ALB_KIND.get(r[3] if len(r) > 3 else '', ''), 'status': ''})
    return out

def upcoming(year, prev=()):
    """두 리그 예정 경기 (날짜·시간순). 한쪽이 실패하면 그 리그는 지난번 목록(prev)에서 아직 안 지난 경기를 쓴다"""
    today = datetime.now().strftime('%Y-%m-%d')
    out, warns = [], []
    def alb():
        if SKIP_ALB: raise OSError('SKIP_ALB=1')
        return alb_upcoming(today)
    for name, f in (('정왕', lambda: jw_upcoming(year, today)), ('안양', alb)):
        try: out += f()
        except Exception as e:
            keep = [g for g in prev if g['league'] == name and g['date'] >= today]
            out += keep
            if name != '안양' or not SKIP_ALB:
                warns.append(f'{name} 예정 경기 수집 실패({e}) — 지난 목록 {len(keep)}경기 유지')
    out.sort(key=lambda g: (g['date'], g['time']))
    return out, warns

def alb_box(g, refresh=False):
    url = f"{ALB_HOST}/z/view.php?id=game&no={g['no']}"
    t = cached(f"alb_{g['no']}", url, 'cp949', refresh)
    tb = tables(t)
    head = next((rows for tag, rows in tb if rows and '◆' in rows[0][0] and len(rows) >= 4), None)
    if not head: raise ValueError(f"안양 {g['no']}: 스코어 표를 찾지 못함")
    comp = [s.strip() for s in head[0][0].split('◆')]
    sc = head[2:4]
    teams = [sc[0][0], sc[1][0]]
    if TEAM not in teams: raise ValueError(f"안양 {g['no']}: {TEAM} 없음 {teams}")
    me = teams.index(TEAM); op = 1 - me
    def lrow(r):
        # [팀, 1..9회, R, H, E, B, HR] — 빈 이닝은 ''
        v = r[1:]; tail = v[-5:]
        return {'inn': [x for x in v[:-5] if x != ''], 'r': int(num(tail[0])), 'h': int(num(tail[1])),
                'e': int(num(tail[2])), 'b': int(num(tail[3]))}
    ls = [lrow(r) for r in sc]
    # 상대 기권·불참: 점수 칸에 '기권승'/'몰수승' 같은 문자, 점수는 0:0 으로 남음
    forfeit = next((x for x in sc[me] if x in ('기권승', '기권패', '몰수승', '몰수패')), '')

    batters = []
    for tag, rows in tb:
        if rows and rows[0][0] == TEAM and '타석' in rows[0]:
            for r in rows[1:]:
                if not r[0] or not r[0].isdigit() and r[0] not in ('PH', 'PR', 'F'): continue
                stats = r[-6:]          # 타석 타수 득점 안타 타점 통산타율
                # '=4회콜드', '=역전' 같은 경기 종료 메모는 타석 아님
                pas = [x for x in r[3:-6] if x not in ('-', '//', '') and not x.startswith('=')]
                b = {'order': r[0], 'name': r[1], 'no': '', 'pos': r[2], 'pas': pas,
                     'pa': int(num(stats[0])), 'ab': int(num(stats[1])), 'r': int(num(stats[2])),
                     'h': int(num(stats[3])), 'rbi': int(num(stats[4])),
                     'sb': sum(p.count('도루') - p.count('도루실패') for p in pas)}
                add_pa_counts(b, pas)
                batters.append(b)

    # 타자 합계 칸이 통째로 비어 있는 경기(2025-10-18 등) → 타석 결과로 타석·타수·안타 재계산 (득점·타점은 알 수 없음)
    if batters and not any(b['pa'] for b in batters):
        for b in batters:
            ks = [pa_kind(p) for p in b['pas']]
            sac = sum('희' in p for p in b['pas'])
            b['pa'] = len(ks)
            b['ab'] = len(ks) - ks.count('BB') - ks.count('HBP') - sac
            b['h'] = sum(k in ('1B', '2B', '3B', 'HR') for k in ks)
        if not ls[me]['h']: ls[me]['h'] = sum(b['h'] for b in batters)

    pitchers = []
    for tag, rows in tb:
        if rows and rows[0][:2] == ['팀', '선수']:
            hdr = [h.replace(' ', '') for h in rows[0]]; ix = {h: k for k, h in enumerate(hdr)}
            for r in rows[1:]:
                if r[0] != TEAM: continue
                # 교체: '선발'·'완투' 또는 '31'(3회 1번타자 때 등판) 같은 코드 → 정왕 표기(선발/구원)에 맞춤
                role = r[ix['교체']]
                role = role if role in ('선발', '완투') else '구원'
                dec = r[ix['결과']]
                dec = {'N/D': '', 'S': '세'}.get(dec, dec)
                pitchers.append({'name': r[1], 'no': '', 'role': role, 'dec': dec,
                                 'outs': ip_to_outs(r[ix['이닝']]), 'bf': int(num(r[ix['타자']])),
                                 'np': int(num(r[ix['투구']])), 'h': int(num(r[ix['안타']])),
                                 'hr': int(num(r[ix['홈런']])), 'bb': int(num(r[ix['4구']])),
                                 'hbp': int(num(r[ix['사구']])), 'so': int(num(r[ix['삼진']])),
                                 'r': int(num(r[ix['실점']])), 'er': int(num(r[ix['자책']]))})

    # 안양은 투수 세부 기록이 비어있는 경기가 있음 → 실점 합이 상대 득점과 안 맞으면 미완성 표시
    pitch_complete = sum(p['r'] for p in pitchers) == ls[op]['r'] and any(p['outs'] for p in pitchers)
    if not pitch_complete and len(pitchers) == 1:
        # 투수 1명이면 박스스코어로 이닝·피안타·실점은 확정 가능
        p = pitchers[0]
        p['outs'] = p['outs'] or len(ls[op]['inn']) * 3
        p['h'] = p['h'] or ls[op]['h']; p['r'] = p['r'] or ls[op]['r']
        if not p['dec'] and ls[me]['r'] != ls[op]['r']:      # 혼자 던졌으면 승패는 확정
            p['dec'] = '승' if ls[me]['r'] > ls[op]['r'] else '패'

    dm = re.match(r'(\d{4})-(\d{2})-(\d{2})', g['date'])
    dow = DOW[datetime(int(dm.group(1)), int(dm.group(2)), int(dm.group(3))).weekday()]
    # 머리글: '2026년 ◆ 연합회장기 ◆ 카테고리… ◆ 통합 ◆ 석수 ◆ 승인 된 경기입니다.'
    # 리그 시즌은 달력 연도와 다를 수 있음 (2026-04-11 경기가 '2025년' 시즌 소속) → 시즌 누적 대조용으로 보관
    return {'id': f"alb-{g['no']}", 'league': '안양', 'comp': comp[1] if len(comp) > 1 else '', 'div': g['cat'],
            'league_season': comp[0].replace('년', ''),
            'date': g['date'], 'dow': dow, 'time': g['time'],
            'opp': teams[op], 'home': me == 1,
            'scored': ls[me]['r'], 'allowed': ls[op]['r'], 'line': {'ay': ls[me], 'opp': ls[op]},
            'batters': batters, 'pitchers': pitchers, 'pitch_complete': pitch_complete or bool(forfeit),
            'forfeit': forfeit, 'src': url}

# --- 집계 ---
def result(g):
    if g.get('forfeit'): return g['forfeit'][-1]          # '기권승' → '승'
    return '승' if g['scored'] > g['allowed'] else ('패' if g['scored'] < g['allowed'] else '무')

BAT_KEYS = ('pa', 'ab', 'h', 'd2', 'd3', 'hr', 'rbi', 'r', 'sb', 'bb', 'hbp', 'so')
PIT_KEYS = ('outs', 'bf', 'h', 'hr', 'bb', 'hbp', 'so', 'r', 'er')

def agg_batters(games):
    out = {}
    for g in games:
        for b in g['batters']:
            d = out.setdefault(b['name'], dict(name=b['name'], g=0, **{k: 0 for k in BAT_KEYS}))
            d['g'] += 1
            for k in BAT_KEYS: d[k] += b.get(k, 0)
    res = []
    for d in out.values():
        ab, h = d['ab'], d['h']
        tb = h + d['d2'] + 2 * d['d3'] + 3 * d['hr']
        obp_den = ab + d['bb'] + d['hbp']
        d['avg'] = round(h / ab, 3) if ab else 0
        d['obp'] = round((h + d['bb'] + d['hbp']) / obp_den, 3) if obp_den else 0
        d['slg'] = round(tb / ab, 3) if ab else 0
        d['ops'] = round(d['obp'] + d['slg'], 3)
        res.append(d)
    return sorted(res, key=lambda x: -x['pa'])

def agg_pitchers(games):
    out = {}
    for g in games:
        for p in g['pitchers']:
            d = out.setdefault(p['name'], dict(name=p['name'], g=0, w=0, l=0, s=0, **{k: 0 for k in PIT_KEYS}))
            d['g'] += 1
            d['w'] += p['dec'] == '승'; d['l'] += p['dec'] == '패'; d['s'] += p['dec'] in ('세', '세이브', 'S')
            for k in PIT_KEYS: d[k] += p.get(k, 0)
    res = []
    for d in out.values():
        ip_dec = d['outs'] / 3
        d['ip'] = outs_to_ip(d['outs'])
        d['era'] = round(d['er'] * 7 / ip_dec, 2) if ip_dec else 0     # 사회인 7이닝 기준
        d['whip'] = round((d['h'] + d['bb'] + d['hbp']) / ip_dec, 2) if ip_dec else 0
        res.append(d)
    return sorted(res, key=lambda x: -x['outs'])

def legacy_game(g):
    """기존 index.html 이 읽는 games 형식"""
    m, d = g['date'][5:7], g['date'][8:10]
    res = result(g)
    return {'date': f"{m}.{d} ({g['dow']})", 'year': g['date'][:4], 'league': g['league'], 'opp': g['opp'],
            'scored': g['scored'], 'allowed': g['allowed'], 'result': res, 'id': g['id']}

def legacy_batter(b):
    return {k: b[k] for k in ('name', 'pa', 'ab', 'h', 'rbi', 'r', 'sb', 'avg')}

def legacy_pitcher(p):
    return {'name': p['name'], 'g': p['g'], 'ip': p['ip'], 'h': p['h'], 'bb': p['bb'] + p['hbp'], 'so': p['so'],
            'r': p['r'], 'er': p['er'], 'era': p['era'], 'w': p['w'], 'l': p['l'], 's': p['s']}

# --- 메인 ---
SEASON_DIR = os.path.join(SCRIPT_DIR, 'seasons')     # 지난 시즌: seasons/YYYY.json (한 번 받아두면 끝)

# 안양 사이트(alb.or.kr)는 해외 접속을 막는다 — GitHub Actions 에서는 SKIP_ALB=1 로 건너뛰고 지난 data.json 의 안양 기록을 그대로 쓴다
SKIP_ALB = os.environ.get('SKIP_ALB') == '1'

def scrape_year(year, refresh=False, ay_fallback=None):
    """ay_fallback: 안양 사이트에 못 닿을 때 대신 쓸 지난 안양 경기 목록. None 이면 실패를 그대로 올린다(--archive)"""
    games, warns = [], []
    print(f'[정왕] {year} 경기 목록...')
    for g in jw_game_list(year):
        if not g['done']: continue
        try: games.append(jw_box(g, refresh)); print('  ', g['date'], 'OK')
        except Exception as e: warns.append(str(e)); print('  ', g['date'], '실패:', e)

    print(f'[안양] {year} 경기 목록...')
    try:
        if SKIP_ALB: raise OSError('SKIP_ALB=1')
        alb_list = alb_game_list(year)
    except OSError as e:
        if ay_fallback is None: raise
        print(f'   안양 사이트 접속 안 됨({e}) → 지난 기록 {len(ay_fallback)}경기 그대로 사용')
        games += ay_fallback
        alb_list = None
    for g in alb_list or []:
        try: games.append(alb_box(g, refresh)); print('  ', g['date'], 'OK')
        except Exception as e: warns.append(str(e)); print('  ', g['date'], '실패:', e)
    if alb_list is None: warns.append('안양 사이트 접속 안 됨 — 안양은 지난 수집분 그대로')

    games.sort(key=lambda g: (g['date'], g['time']))
    for g in games:
        g['result'] = result(g)
        for b in g['batters']:
            if len(b['pas']) > b['pa']:
                warns.append(f"{g['date']} {g['league']} {b['name']}: 타석 {b['pa']} < 타석결과 {len(b['pas'])}개 — 파서 확인 필요 {b['pas']}")
            elif len(b['pas']) < b['pa']:
                warns.append(f"{g['date']} {g['league']} {b['name']}: 타석 {b['pa']}인데 결과 {len(b['pas'])}개만 기록됨 (리그 원본 누락)")
        if not g['pitch_complete']: warns.append(f"{g['date']} {g['league']} vs {g['opp']}: 투수 기록 미입력(박스스코어로 일부 보정)")
    return games, warns, alb_list is not None

# --- 개인 시상 부문 (리그 전체 순위) ---
# (키, 이름, 타자/투수, 사이트 정렬값, 낮을수록 좋음, 규정 적용, 사이트 열 머리, 우리 기록 키)
JW_AWARDS = [
    ('avg', '타율',   'batter',  'AVERAGE',            False, True,  '타율',       'avg'),
    ('hr',  '홈런',   'batter',  'HOME_RUNS',          False, False, '홈런(G홈런)', 'hr'),
    ('rbi', '타점',   'batter',  'RUNS_BATTED_IN',     False, False, '타점',       'rbi'),
    ('h',   '안타',   'batter',  'TOTAL_HITS',         False, False, '안타',       'h'),
    ('r',   '득점',   'batter',  'RUNS_SCORED',        False, False, '득점',       'r'),
    ('sb',  '도루',   'batter',  'STOLEN_BASES',       False, False, '도루',       'sb'),
    ('w',   '다승',   'pitcher', 'WINS',               False, False, '승리',       'w'),
    ('era', '평균자책', 'pitcher', 'EARNED_RUN_AVERAGE', True,  True,  '평균자책점',  'era'),
    ('so',  '탈삼진', 'pitcher', 'STRIKE_OUTS',        False, False, '삼진',       'so'),
]

def ranked(vals):
    """이미 정렬된 값 목록 → 공동 순위(1,2,2,4)"""
    out, prev = [], None
    for i, v in enumerate(vals):
        if v != prev: rank, prev = i + 1, v
        out.append(rank)
    return out

def jw_awards(year, div_games, my):
    """정왕 우리 부(정왕토요4부 등) 개인 부문별 상위 5명 + 우리 팀 최고 선수.
    기록실 PC 페이지는 30명씩 나뉘어 있어 부문마다 정렬된 첫 페이지만 받는다(부문당 1회 요청).
    my: 우리 팀 정왕 시즌 집계 {'batters': […], 'pitchers': […]} — 30위 밖일 때 우리 최고 기록 계산용"""
    if not div_games: return None
    comp, div = div_games[-1]['comp'], div_games[-1]['div']
    url = JW_HOST + '/record/getPlayerRecordList.hs'
    t = fetch(url, referer=JW_HOST)
    opt = lambda name: (re.search(r'<option value="(\d+)"[^>]*>\s*' + re.escape(name) + r'\s*</option>', t) or [None, None])[1]
    top_seq = opt(comp)
    if not top_seq: raise ValueError(f'정왕 기록실: 리그 {comp} 를 찾지 못함')
    # 하위 리그 목록은 상위 리그에 따라 바뀜 → 그 상위 리그로 한 번 조회한 페이지에서 찾는다
    base = {'num': 1, 'action': '/record/getPlayerRecordList.hs', 'playerSeq': '', 'recordType': 'basic',
            'infoType': 'DEFAULT', 'leagueCategory': 'NORMAL', 'searchYear': year,
            'searchTopLeagueSeq': top_seq, 'searchKeyword': ''}
    t = fetch(url, referer=url, data={**base, 'searchLowerLeagueSeq': '', 'playerType': 'batter',
                                      'orderCondition': 'AVERAGE', 'orderType': 'DESC', 'applyRagulationPlate': 'N'})
    low_seq = opt(div)
    if not low_seq: raise ValueError(f'정왕 기록실: {div} 를 찾지 못함')
    base['searchLowerLeagueSeq'] = low_seq
    team_g = len(div_games)
    cats = []
    for key, label, ptype, order, asc, qual, col, mykey in JW_AWARDS:
        t = fetch(url, referer=url, data={**base, 'playerType': ptype, 'orderCondition': order,
                                          'orderType': 'ASC' if asc else 'DESC',
                                          # 규정 적용: 타자는 Plate, 투수는 Innings (사이트 폼 이름이 다름)
                                          'applyRagulation' + ('Plate' if ptype == 'batter' else 'Innings'): 'Y' if qual else 'N'})
        rows = next((rows for tag, rows in tables(t) if rows and rows[0][:2] == ['순위', '선수명']), [])
        if not rows: raise ValueError(f'정왕 기록실 {label}: 표 없음')
        ix = next(k for k, h in enumerate(rows[0]) if h.split(' ')[0] == col)
        per = re.search(r'규정(?:타석|이닝)은\s*([\d.]+)', strip(t))
        players = []
        for r in rows[1:]:
            if len(r) <= ix: continue
            nm, no = name_no(r[1])
            players.append({'name': nm, 'team': r[2], 'v': num(r[ix].split()[0])})
        if not qual: players = [p for p in players if p['v'] > 0]      # 누적 부문에서 0개는 순위에서 뺀다
        for p, rk in zip(players, ranked([p['v'] for p in players])): p['rank'] = rk
        top = [p for p in players if p['rank'] <= 5]
        more = max(0, len(top) - 7); top = top[:7]       # 공동 5위가 너무 많으면(홈런 1개 20명 등) 7명까지만, 나머지는 인원수
        mine, short = next((p for p in players if p['team'] == TEAM), None), None
        if not mine:      # 첫 페이지(30명) 밖 — 우리 집계에서 최고 기록 (규정 부문은 규정 충족자만)
            pool = my['batters' if ptype == 'batter' else 'pitchers']
            if qual and per:
                need = float(per.group(1)) * team_g
                amt = lambda p: p['pa'] if ptype == 'batter' else round(p['outs'] / 3, 1)
                if pool and not any(amt(p) >= need for p in pool):    # 규정 채운 사람 없음 → 가장 가까운 선수
                    b = max(pool, key=amt)
                    short = {'name': b['name'], 'have': amt(b), 'need': need, 'v': b[mykey]}
                pool = [p for p in pool if amt(p) >= need]
            pool = [p for p in pool if p.get(mykey) or (key == 'era' and p['outs'])]
            if pool:
                b = sorted(pool, key=lambda p: p[mykey] if asc else -p[mykey])[0]
                mine = {'name': b['name'], 'team': TEAM, 'v': b[mykey], 'rank': None}
        cats.append({'key': key, 'label': label, 'asc': asc,
                     'qual': f"규정{'타석' if ptype == 'batter' else '이닝'} 경기당 {per.group(1)}" if qual and per else '',
                     'top': top, 'more': more, 'mine': mine, 'short': short})
    return {'comp': comp, 'div': div, 'cats': cats}

def season_stats(games):
    jw = [g for g in games if g['league'] == '정왕']
    ay = [g for g in games if g['league'] == '안양']
    return {'all': {'batters': agg_batters(games), 'pitchers': agg_pitchers(games)},
            'jw': {'batters': agg_batters(jw), 'pitchers': agg_pitchers(jw)},
            'ay': {'batters': agg_batters(ay), 'pitchers': agg_pitchers(ay)}}

def record(games):
    rs = [result(g) for g in games]; w, l = rs.count('승'), rs.count('패')
    return {'g': len(games), 'w': w, 'l': l, 'd': len(games) - w - l,
            'rs': sum(g['scored'] for g in games), 'ra': sum(g['allowed'] for g in games)}

def history(seasons):
    """연도별 팀 성적 + 선수 연도별 기록(전 리그 합산) — 홈 드롭다운·선수 연도별 그래프용"""
    team, bat, pit = [], [], []
    for y, games in sorted(seasons.items()):
        jw = [g for g in games if g['league'] == '정왕']; ay = [g for g in games if g['league'] == '안양']
        team.append({'year': y, 'all': record(games), 'jw': record(jw), 'ay': record(ay)})
        for b in agg_batters(games): bat.append({'year': y, **b})
        for p in agg_pitchers(games): pit.append({'year': y, **p})
    return {'team': team, 'batters': bat, 'pitchers': pit}

def write_json(path, obj, indent=1):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)

def load_seasons(exclude):
    out = {}
    if os.path.isdir(SEASON_DIR):
        for fn in sorted(os.listdir(SEASON_DIR)):
            m = re.fullmatch(r'(\d{4})\.json', fn)
            if m and int(m.group(1)) != exclude:
                with open(os.path.join(SEASON_DIR, fn), encoding='utf-8') as f:
                    out[int(m.group(1))] = json.load(f)['box']
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=datetime.now().year)
    ap.add_argument('--refresh', action='store_true')
    ap.add_argument('--archive', metavar='YYYY-YYYY', help='지난 시즌을 seasons/YYYY.json 으로 저장 (예: 2019-2025)')
    a = ap.parse_args()

    if a.archive:
        y1, y2 = (int(x) for x in a.archive.split('-'))
        os.makedirs(SEASON_DIR, exist_ok=True)
        for y in range(y1, y2 + 1):
            games, warns, _ = scrape_year(y, a.refresh)
            if not games: print(f'  {y}: 경기 없음'); continue
            write_json(os.path.join(SEASON_DIR, f'{y}.json'),
                       {'year': y, 'updated': datetime.now().strftime('%Y-%m-%d %H:%M'), 'record': record(games),
                        'box': games, 'stats': season_stats(games), 'warnings': warns}, indent=None)
            r = record(games)
            print(f"→ {y}: {r['g']}경기 {r['w']}승 {r['l']}패 {r['d']}무, 경고 {len(warns)}건")
        return

    base = {}
    if os.path.exists(BASE_JSON):
        with open(BASE_JSON, encoding='utf-8') as f: base = json.load(f)
    same_season = base.get('season') == a.year
    prev_ay = [g for g in base.get('box', []) if g['league'] == '안양'] if same_season else []

    games, warns, ay_ok = scrape_year(a.year, a.refresh, ay_fallback=prev_ay)
    jw = [g for g in games if g['league'] == '정왕']
    ay = [g for g in games if g['league'] == '안양']
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    # 안양 기록이 언제 받은 것인지 — 못 받았으면 지난 값을 이어받는다(화면에 「안양 M.D 기준」 표시)
    ay_updated = now if ay_ok else (base.get('ay_updated') or base.get('updated', ''))

    st = season_stats(games)
    bat_all, pit_all = st['all']['batters'], st['all']['pitchers']
    past = load_seasons(a.year)
    print('[예정 경기] 두 리그 일정...')
    up, up_warns = upcoming(a.year, prev=base.get('upcoming', []) if same_season else [])
    for g in up: print('  ', g['date'], g['time'], g['league'], 'vs', g['opp'], g['place'])
    warns += up_warns
    # 개인 시상 부문 — 우리 정규 리그 부(가장 많이 뛴 리그/부)만. 실패하면 지난 값 유지
    awards = dict(base.get('awards', {})) if same_season else {}
    if jw:
        from collections import Counter
        cd = Counter((g['comp'], g['div']) for g in jw).most_common(1)[0][0]
        div_games = [g for g in jw if (g['comp'], g['div']) == cd]
        print(f'[개인 순위] 정왕 {cd[0]} / {cd[1]}...')
        try:
            awards['정왕'] = {**jw_awards(a.year, div_games, {'batters': agg_batters(div_games), 'pitchers': agg_pitchers(div_games)}),
                             'updated': now}
        except Exception as e:
            warns.append(f'정왕 개인 순위 못 받음({e}) — 지난 값 그대로'); print('   실패:', e)
    out = {
        'updated': now,
        'ay_updated': ay_updated,
        'ay_live': ay_ok,        # 이번 실행에서 안양 사이트를 실제로 받았나 (False = 지난 수집분)
        'season': a.year,
        'source': 'scrape',
        # 기존 index.html 호환 필드
        'games': [legacy_game(g) for g in games],
        'batters': [legacy_batter(b) for b in bat_all],
        'pitchers': [legacy_pitcher(p) for p in pit_all],
        'jw_batters': [legacy_batter(b) for b in st['jw']['batters']],
        'jw_pitchers': [legacy_pitcher(p) for p in st['jw']['pitchers']],
        'ay_batters': [legacy_batter(b) for b in st['ay']['batters']],
        'ay_pitchers': [legacy_pitcher(p) for p in st['ay']['pitchers']],
        'past_ay_games': base.get('past_ay_games', []),
        'jw_seasons': base.get('jw_seasons', []),
        'past_batters': base.get('past_batters', []),
        # 모바일 대시보드용 확장 필드
        'box': games,
        'upcoming': up,          # 예정 경기 (오늘 이후, 리그 일정표 기준)
        'awards': awards,        # 리그별 개인 부문 상위 5 + 우리 팀 최고 {'정왕': {comp, div, cats, updated}}
        'stats': st,
        'years': sorted(list(past) + [a.year], reverse=True),     # 지난 시즌 상세는 seasons/YYYY.json
        'history': history({**past, a.year: games}),
        'warnings': warns,
    }
    write_json(OUT_PATH, out)
    r = record(games)
    print(f"\n완료: {len(games)}경기 (정왕 {len(jw)} / 안양 {len(ay)}) {r['w']}승 {r['l']}패 {r['d']}무 → {OUT_PATH}")
    print(f"   지난 시즌 {len(past)}개 연도 기록 포함: {sorted(past)}")
    for m in warns: print('  ⚠', m)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('오류:', e); sys.exit(1)
