#!/usr/bin/env python3
"""data_scraped.json 검증 — 경기별 합산 vs 리그 사이트 시즌 누적, 그리고 기존 data.json(엑셀) 비교"""
import sys, os, re, json, urllib.parse
import scrape_leagues as S

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def load(p):
    with open(os.path.join(SCRIPT_DIR, p), encoding='utf-8') as f: return json.load(f)

def diff_table(title, mine, site, keys):
    """mine/site: {이름: {키: 값}}. 다른 칸만 출력, 일치 개수 반환"""
    print(f'\n=== {title} ===')
    ok = bad = 0
    for nm in sorted(set(mine) | set(site)):
        a, b = mine.get(nm), site.get(nm)
        if not a or not b:
            print(f'  {nm}: {"사이트에만" if b else "스크랩에만"} 있음'); bad += 1; continue
        d = [f'{k} {a.get(k,0)}≠{b.get(k,0)}' for k in keys if a.get(k, 0) != b.get(k, 0)]
        if d: print(f'  {nm}: ' + ', '.join(d)); bad += 1
        else: ok += 1
    print(f'  → 일치 {ok}명 / 불일치 {bad}명')
    return bad

# --- 정왕 시즌 누적 (모바일 팀 페이지: 이름 칸과 숫자 표가 분리돼 있어 순서로 맞춤) ---
def jw_site(kind, year):
    page = 'getBatterRecord' if kind == 'bat' else 'getPitcherRecord'
    t = S.fetch(f"{S.JW_HOST}/m/teamPage/scheduleRecord/{page}.hs?teamSeq={S.JW_TEAM}&searchYear={year}",
                referer=S.JW_HOST, ua=S.UA_MOBILE)
    txt = S.strip(t)
    first = '타율 ▼' if kind == 'bat' else '평균자책점'
    i = txt.find('순위 선수명'); j = txt.find(first, i)
    names = re.findall(r'([가-힣A-Za-z]+) \(\d+\)', txt[i:j])
    for tag, rows in S.tables(t):
        if rows and rows[0][:1] == [first]:
            ix = {h: k for k, h in enumerate(rows[0])}
            out = {}
            for nm, r in zip(names, rows[1:]):
                v = lambda h: int(S.num(r[ix[h]]))
                if kind == 'bat':
                    out[nm] = {'g': v('경기'), 'pa': v('타석'), 'ab': v('타수'), 'h': v('안타'), 'd2': v('2루타'),
                               'd3': v('3루타'), 'hr': int(S.num(r[ix['홈런(G홈런)']].split()[0])), 'rbi': v('타점'),
                               'r': v('득점'), 'sb': v('도루'), 'bb': v('볼넷'), 'hbp': v('사구'), 'so': v('삼진')}
                else:
                    out[nm] = {'g': v('경기'), 'w': v('승리'), 'l': v('패배'), 'outs': S.ip_to_outs(r[ix['이닝']]),
                               'h': v('피안타'), 'bb': v('볼넷'), 'so': v('삼진'), 'r': v('실점'), 'er': v('자책점')}
            return out
    return {}

# --- 안양 시즌 누적 (연합회장기만 집계됨) ---
def alb_site(year):
    q = lambda s: urllib.parse.quote(s.encode('cp949'))
    t = S.fetch(f"{S.ALB_HOST}/s/stand_bat/index.php?id=stats&league={q('연합회장기')}&sc=2&gyear={year}"
                f"&team={q(S.TEAM)}&order=hit&sort=desc&mode=team_stats", enc='cp949')
    # 머리행과 데이터 행이 서로 다른 표에 있음 → 전체 행을 모아서 처리
    allrows = [r for tag, rows in S.tables(t) for r in rows]
    hdr = next((r for r in allrows if r[:2] == ['R.', 'PLAYERS']), None)
    if not hdr: return {}
    ix = {h: k for k, h in enumerate(hdr)}
    out = {}
    for r in allrows:
        if len(r) <= ix['RUN'] or r[ix['TEAMS']] != S.TEAM: continue   # 데이터 행은 머리행보다 한 칸 짧음
        v = lambda h: int(S.num(r[ix[h]]))
        out[r[ix['PLAYERS']]] = {'g': v('PG'), 'pa': v('TPA'), 'ab': v('AB'), 'h': v('HIT'), 'd2': v('2B'),
                                 'd3': v('3B'), 'hr': v('HR'), 'rbi': v('RBI'), 'r': v('RUN'),
                                 'bb': v('BB'), 'hbp': v('HBP'), 'so': v('SO')}
    return out

def main():
    d = load('data_scraped.json'); year = d['season']
    box = d['box']
    bad = 0

    jw = [g for g in box if g['league'] == '정왕']
    mine = {b['name']: b for b in S.agg_batters(jw)}
    bad += diff_table(f'정왕 타자: 경기별 합산 vs 사이트 시즌 누적 ({len(jw)}경기)', mine, jw_site('bat', year),
                      ('g', 'pa', 'ab', 'h', 'd2', 'd3', 'hr', 'rbi', 'r', 'sb', 'bb', 'hbp', 'so'))
    mine = {p['name']: p for p in S.agg_pitchers(jw)}
    bad += diff_table('정왕 투수: 경기별 합산 vs 사이트 시즌 누적', mine, jw_site('pit', year),
                      ('g', 'w', 'l', 'outs', 'h', 'r', 'er', 'so'))

    ay = [g for g in box if g['league'] == '안양' and g['comp'] == '연합회장기' and g.get('league_season') == str(year)]
    if not d.get('ay_live', True):
        # 안양 사이트에 못 닿아(해외 서버 등) 지난 수집분을 그대로 쓴 경우 — 이미 검증 거친 값이라 대조 생략
        print(f"\n=== 안양: 이번엔 못 받음 — {d.get('ay_updated')} 수집분 그대로, 대조 생략 ===")
    else:
        mine = {b['name']: b for b in S.agg_batters(ay)}
        bad += diff_table(f'안양 타자: 연합회장기 경기별 합산 vs 사이트 시즌 누적 ({len(ay)}경기)', mine, alb_site(year),
                          ('g', 'pa', 'ab', 'h', 'd2', 'd3', 'hr', 'rbi', 'r', 'bb', 'hbp', 'so'))

    # --- 기존 엑셀과 경기 결과 비교 (data.json 은 업데이트 후 스크랩 결과로 바뀌므로 엑셀 시절 백업 사용) ---
    ref = 'data_엑셀백업.json' if os.path.exists(os.path.join(SCRIPT_DIR, 'data_엑셀백업.json')) else 'data.json'
    print(f'\n=== 기존 {ref}(엑셀) 경기 결과 비교 ===')
    old = load(ref)
    new = {(g['league'], g['date'][:5]): g for g in d['games']}
    for g in old.get('games', []):
        k = (g['league'], g['date'][:5])
        n = new.get(k)
        if not n: print(f'  {k} {g["opp"]}: 스크랩에 없음'); bad += 1
        elif (n['scored'], n['allowed']) != (g['scored'], g['allowed']):
            print(f'  {k} {g["opp"]}: 엑셀 {g["scored"]}:{g["allowed"]} ≠ 스크랩 {n["scored"]}:{n["allowed"]}'); bad += 1
    extra = [g for g in d['games'] if (g['league'], g['date'][:5]) not in {(o['league'], o['date'][:5]) for o in old.get('games', [])}]
    print(f'  엑셀 {len(old.get("games", []))}경기 중 점수 불일치/누락 위 목록 외 모두 일치')
    print(f'  스크랩에서 새로 생긴 경기 {len(extra)}개: ' + ', '.join(f'{g["date"][:5]} {g["league"]} {g["opp"]}' for g in extra))

    print('\n=== 경고 ===')
    for w in d.get('warnings', []): print('  ⚠', w)
    print(f'\n검증 끝: 불일치 {bad}건')
    return bad

if __name__ == '__main__':
    try:
        sys.exit(1 if main() else 0)     # 불일치가 있으면 업데이트.bat 이 업로드 전에 멈춤
    except Exception as e:
        print('오류:', e); sys.exit(1)
