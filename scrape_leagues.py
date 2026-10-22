#!/usr/bin/env python3
"""AY션샤인 리그 스크래퍼  정왕(shbaseball.co.kr) + 안양(alb.or.kr) → data_scraped.json

사용법:
  python scrape_leagues.py              # 올해 시즌, 캐시된 경기는 다시 받지 않음
  python scrape_leagues.py --year 2026
  python scrape_leagues.py --refresh    # 경기 박스스코어 캐시 무시하고 전부 다시 받기
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
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        raw = r.read()
        if not r.headers.get('Transfer-Encoding'): raw = dechunk(raw)
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
            if EVENT.search(tok) and pas: pas[-1] += ',' + tok
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
                      'comp': lg.group(1) if lg else '', 'div': lg.group(2) if lg else ''})
    return games

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

    batters = []
    for tag, rows in tb:
        if rows and rows[0][0] == TEAM and '타석' in rows[0]:
            for r in rows[1:]:
                if not r[0] or not r[0].isdigit() and r[0] not in ('PH', 'PR', 'F'): continue
                stats = r[-6:]          # 타석 타수 득점 안타 타점 통산타율
                pas = [x for x in r[3:-6] if x not in ('-', '//', '')]
                b = {'order': r[0], 'name': r[1], 'no': '', 'pos': r[2], 'pas': pas,
                     'pa': int(num(stats[0])), 'ab': int(num(stats[1])), 'r': int(num(stats[2])),
                     'h': int(num(stats[3])), 'rbi': int(num(stats[4])),
                     'sb': sum(p.count('도루') - p.count('도루실패') for p in pas)}
                add_pa_counts(b, pas)
                batters.append(b)

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
            'batters': batters, 'pitchers': pitchers, 'pitch_complete': pitch_complete,
            'src': url}

# --- 집계 ---
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
    res = '승' if g['scored'] > g['allowed'] else ('패' if g['scored'] < g['allowed'] else '무')
    return {'date': f"{m}.{d} ({g['dow']})", 'year': g['date'][:4], 'league': g['league'], 'opp': g['opp'],
            'scored': g['scored'], 'allowed': g['allowed'], 'result': res, 'id': g['id']}

def legacy_batter(b):
    return {k: b[k] for k in ('name', 'pa', 'ab', 'h', 'rbi', 'r', 'sb', 'avg')}

def legacy_pitcher(p):
    return {'name': p['name'], 'g': p['g'], 'ip': p['ip'], 'h': p['h'], 'bb': p['bb'] + p['hbp'], 'so': p['so'],
            'r': p['r'], 'er': p['er'], 'era': p['era'], 'w': p['w'], 'l': p['l'], 's': p['s']}

# --- 메인 ---
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=datetime.now().year)
    ap.add_argument('--refresh', action='store_true')
    a = ap.parse_args()

    games, warns = [], []
    print(f'[정왕] {a.year} 경기 목록...')
    for g in jw_game_list(a.year):
        if not g['done']: continue
        try: games.append(jw_box(g, a.refresh)); print('  ', g['date'], 'OK')
        except Exception as e: warns.append(str(e)); print('  ', g['date'], '실패:', e)

    print(f'[안양] {a.year} 경기 목록...')
    for g in alb_game_list(a.year):
        try: games.append(alb_box(g, a.refresh)); print('  ', g['date'], 'OK')
        except Exception as e: warns.append(str(e)); print('  ', g['date'], '실패:', e)

    games.sort(key=lambda g: (g['date'], g['time']))
    for g in games:
        for b in g['batters']:
            if len(b['pas']) > b['pa']:
                warns.append(f"{g['date']} {g['league']} {b['name']}: 타석 {b['pa']} < 타석결과 {len(b['pas'])}개 — 파서 확인 필요 {b['pas']}")
            elif len(b['pas']) < b['pa']:
                warns.append(f"{g['date']} {g['league']} {b['name']}: 타석 {b['pa']}인데 결과 {len(b['pas'])}개만 기록됨 (리그 원본 누락)")
        if not g['pitch_complete']: warns.append(f"{g['date']} {g['league']} vs {g['opp']}: 투수 기록 미입력(박스스코어로 일부 보정)")
    jw = [g for g in games if g['league'] == '정왕']
    ay = [g for g in games if g['league'] == '안양']

    base = {}
    if os.path.exists(BASE_JSON):
        with open(BASE_JSON, encoding='utf-8') as f: base = json.load(f)

    bat_all, pit_all = agg_batters(games), agg_pitchers(games)
    out = {
        'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'season': a.year,
        'source': 'scrape',
        # 기존 index.html 호환 필드
        'games': [legacy_game(g) for g in games],
        'batters': [legacy_batter(b) for b in bat_all],
        'pitchers': [legacy_pitcher(p) for p in pit_all],
        'jw_batters': [legacy_batter(b) for b in agg_batters(jw)],
        'jw_pitchers': [legacy_pitcher(p) for p in agg_pitchers(jw)],
        'ay_batters': [legacy_batter(b) for b in agg_batters(ay)],
        'ay_pitchers': [legacy_pitcher(p) for p in agg_pitchers(ay)],
        'past_ay_games': base.get('past_ay_games', []),
        'jw_seasons': base.get('jw_seasons', []),
        'past_batters': base.get('past_batters', []),
        # 모바일 대시보드용 확장 필드
        'box': games,
        'stats': {'all': {'batters': bat_all, 'pitchers': pit_all},
                  'jw': {'batters': agg_batters(jw), 'pitchers': agg_pitchers(jw)},
                  'ay': {'batters': agg_batters(ay), 'pitchers': agg_pitchers(ay)}},
        'warnings': warns,
    }
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    w = sum(g['scored'] > g['allowed'] for g in games)
    print(f'\n완료: {len(games)}경기 (정왕 {len(jw)} / 안양 {len(ay)}) {w}승 {len(games)-w}패 → {OUT_PATH}')
    for m in warns: print('  ⚠', m)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('오류:', e); sys.exit(1)
