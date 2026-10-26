#!/usr/bin/env python3
"""AY션샤인 전체 기록 내보내기  data.json + seasons/*.json → records/

  python export_records.py
  → records/AY션샤인_전체기록.xlsx (openpyxl 있으면, 시트 8개)
  → records/*.csv (엑셀에서 바로 열림, utf-8-sig)
"""
import os, re, csv, json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, 'records')

def load():
    with open(os.path.join(SCRIPT_DIR, 'data.json'), encoding='utf-8') as f: d = json.load(f)
    box = list(d['box'])
    sd = os.path.join(SCRIPT_DIR, 'seasons')
    for fn in sorted(os.listdir(sd)):
        if re.fullmatch(r'\d{4}\.json', fn) and int(fn[:4]) != d['season']:
            with open(os.path.join(sd, fn), encoding='utf-8') as f: box += json.load(f)['box']
    box.sort(key=lambda g: (g['date'], g['time']))
    return d, box

def ip(outs): return f"{outs // 3}.{outs % 3}"

def sum_rows(rows, keys):
    t = {k: 0 for k in keys}
    for r in rows:
        for k in keys: t[k] += r[k]
    return t

def bat_rates(t):
    den = t['ab'] + t['bb'] + t['hbp']; tb = t['h'] + t['d2'] + 2 * t['d3'] + 3 * t['hr']
    avg = t['h'] / t['ab'] if t['ab'] else 0
    obp = (t['h'] + t['bb'] + t['hbp']) / den if den else 0
    slg = tb / t['ab'] if t['ab'] else 0
    return round(avg, 3), round(obp, 3), round(slg, 3), round(obp + slg, 3)

def pit_rates(t):
    i = t['outs'] / 3
    return (round(t['er'] * 7 / i, 2) if i else 0), (round((t['h'] + t['bb'] + t['hbp']) / i, 2) if i else 0)

BK = ['g', 'pa', 'ab', 'h', 'd2', 'd3', 'hr', 'rbi', 'r', 'sb', 'bb', 'hbp', 'so']
PK = ['g', 'w', 'l', 's', 'outs', 'bf', 'h', 'hr', 'bb', 'hbp', 'so', 'r', 'er']
BH = ['경기', '타석', '타수', '안타', '2루타', '3루타', '홈런', '타점', '득점', '도루', '볼넷', '사구', '삼진', '타율', '출루율', '장타율', 'OPS']
PH = ['경기', '승', '패', '세', '이닝', '상대타자', '피안타', '피홈런', '볼넷', '사구', '삼진', '실점', '자책', 'ERA(7이닝)', 'WHIP']

def sheets(d, box):
    S = {}
    S['연도별_팀성적'] = [['연도', '구분', '경기', '승', '패', '무', '득점', '실점', '득실차']] + [
        [t['year'], lg, t[k]['g'], t[k]['w'], t[k]['l'], t[k]['d'], t[k]['rs'], t[k]['ra'], t[k]['rs'] - t[k]['ra']]
        for t in d['history']['team'] for k, lg in (('all', '통합'), ('jw', '정왕'), ('ay', '안양')) if t[k]['g']]
    S['경기목록'] = [['날짜', '요일', '시간', '리그', '대회', '구분', '리그시즌', '상대', '홈/원정', '득점', '실점', '결과', '비고', '기록지']] + [
        [g['date'], g['dow'], g['time'], g['league'], g['comp'], g['div'], g.get('league_season', ''), g['opp'],
         '홈' if g['home'] else '원정', g['scored'], g['allowed'], g['result'],
         g.get('forfeit') or ('' if g['pitch_complete'] else '투수기록 일부 미입력'), g['src']] for g in box]
    hb, hp = d['history']['batters'], d['history']['pitchers']
    S['타자_연도별'] = [['연도', '이름'] + BH] + [
        [b['year'], b['name']] + [b[k] for k in BK] + list(bat_rates(b)) for b in hb]
    S['투수_연도별'] = [['연도', '이름'] + PH] + [
        [p['year'], p['name']] + [p[k] for k in PK[:4]] + [ip(p['outs'])] + [p[k] for k in PK[5:]] + list(pit_rates(p)) for p in hp]
    car = []
    for n in sorted({b['name'] for b in hb}):
        rows = [b for b in hb if b['name'] == n]; t = sum_rows(rows, BK)
        car.append([n, f"{rows[0]['year']}~{rows[-1]['year']}", len(rows)] + [t[k] for k in BK] + list(bat_rates(t)))
    S['타자_통산'] = [['이름', '기간', '시즌수'] + BH] + sorted(car, key=lambda r: -r[4])
    car = []
    for n in sorted({p['name'] for p in hp}):
        rows = [p for p in hp if p['name'] == n]; t = sum_rows(rows, PK)
        car.append([n, f"{rows[0]['year']}~{rows[-1]['year']}", len(rows)] + [t[k] for k in PK[:4]] + [ip(t['outs'])]
                   + [t[k] for k in PK[5:]] + list(pit_rates(t)))
    S['투수_통산'] = [['이름', '기간', '시즌수'] + PH] + sorted(car, key=lambda r: -int(r[7].split('.')[0]) * 3 - int(r[7].split('.')[1]))
    S['타자_경기별'] = [['날짜', '리그', '상대', '결과', '타순', '이름', '포지션', '타석', '타수', '안타', '2루타', '3루타', '홈런', '타점', '득점', '도루', '볼넷', '사구', '삼진', '타석결과']] + [
        [g['date'], g['league'], g['opp'], g['result'], b['order'], b['name'], b['pos']] +
        [b.get(k, 0) for k in ('pa', 'ab', 'h', 'd2', 'd3', 'hr', 'rbi', 'r', 'sb', 'bb', 'hbp', 'so')] + [' / '.join(b['pas'])]
        for g in box for b in g['batters']]
    S['투수_경기별'] = [['날짜', '리그', '상대', '결과', '이름', '등판', '승패', '이닝', '상대타자', '투구수', '피안타', '피홈런', '볼넷', '사구', '삼진', '실점', '자책']] + [
        [g['date'], g['league'], g['opp'], g['result'], p['name'], p['role'], p['dec'], ip(p['outs']),
         p['bf'], p['np'], p['h'], p['hr'], p['bb'], p['hbp'], p['so'], p['r'], p['er']]
        for g in box for p in g['pitchers']]
    return S

def main():
    d, box = load()
    S = sheets(d, box)
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, rows in S.items():
        with open(os.path.join(OUT_DIR, f'{name}.csv'), 'w', encoding='utf-8-sig', newline='') as f:
            csv.writer(f).writerows(rows)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        print('openpyxl 없음 → CSV만 만듦'); return
    wb = Workbook(); wb.remove(wb.active)
    info = wb.create_sheet('안내')
    for r in [['AY션샤인 전체 기록'], [f"갱신 {d['updated']} · {box[0]['date'][:4]}~{d['season']} · {len(box)}경기"],
              ['출처: 시흥시 야구소프트볼협회(정왕) · 안양시야구연합회(안양) 경기기록지 자동 수집'],
              ['ERA는 7이닝 기준. 안양은 투수 세부 기록이 빠진 경기가 있어 ERA가 실제보다 낮을 수 있음'],
              ['연도 = 경기 날짜 기준 (안양 리그시즌과 다를 수 있음, 경기목록 시트의 리그시즌 열 참고)']]:
        info.append(r)
    info['A1'].font = Font(bold=True, size=14); info.column_dimensions['A'].width = 90
    for name, rows in S.items():
        ws = wb.create_sheet(name)
        for r in rows: ws.append(r)
        for c in ws[1]: c.font = Font(bold=True); c.fill = PatternFill('solid', fgColor='DDEBF7')
        ws.freeze_panes = 'A2'; ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            w = max(len(str(c.value or '')) for c in col[:200])
            ws.column_dimensions[col[0].column_letter].width = min(max(6, w * 1.6), 60)
    out = os.path.join(OUT_DIR, 'AY션샤인_전체기록.xlsx')
    wb.save(out)
    print(f'완료: {len(box)}경기 → {out} (+ CSV {len(S)}개)')

if __name__ == '__main__':
    main()
