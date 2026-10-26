/**
 * AY션샤인 참석 투표 · 라인업 저장소 (Google Apps Script 웹 앱)
 *
 * 설치: script.google.com → 새 프로젝트 → 이 코드 붙여넣기 → 저장
 *       → 배포 → 새 배포 → 유형 '웹 앱' / 실행: 나 / 액세스: 모든 사용자 → 배포
 *       → 나온 웹 앱 URL(…/exec)을 index.html 의 ATTEND_API 에 넣기
 * 데이터는 처음 요청 때 내 드라이브에 'AY션샤인 참석·라인업' 시트를 만들어 저장 (시트에서 직접 고쳐도 됨)
 * 팀 암호(선택): 프로젝트 설정 → 스크립트 속성에 PASSCODE 추가하면 입력할 때 암호 필요
 */

const SHEETS = {
  games:   ['id', 'date', 'time', 'opp', 'league', 'place', 'memo', 'by', 'ts', 'deleted'],
  votes:   ['gameId', 'name', 'status', 'ts'],
  lineups: ['gameId', 'json', 'by', 'ts', 'ver'],
  roster:  ['name', 'ts'],
};
const STATUS = ['참석', '불참', '미정'];

function book_() {
  const props = PropertiesService.getScriptProperties();
  let id = props.getProperty('SHEET_ID');
  let ss = id ? SpreadsheetApp.openById(id) : null;
  if (!ss) {
    ss = SpreadsheetApp.create('AY션샤인 참석·라인업');
    props.setProperty('SHEET_ID', ss.getId());
  }
  Object.keys(SHEETS).forEach(name => {
    if (!ss.getSheetByName(name)) {
      const sh = ss.insertSheet(name);
      sh.getRange(1, 1, sh.getMaxRows(), SHEETS[name].length).setNumberFormat('@');   // 날짜·시간이 자동 변환되지 않게 텍스트로
      sh.appendRow(SHEETS[name]);
      sh.setFrozenRows(1);
    }
  });
  const def = ss.getSheetByName('Sheet1') || ss.getSheetByName('시트1');
  if (def && ss.getSheets().length > 1) ss.deleteSheet(def);
  return ss;
}

function rows_(ss, name) {
  const v = ss.getSheetByName(name).getDataRange().getValues();
  const head = v.shift();
  return v.map((r, i) => {
    const o = { _row: i + 2 };
    head.forEach((h, k) => o[h] = r[k] instanceof Date ? Utilities.formatDate(r[k], 'Asia/Seoul', h === 'time' ? 'HH:mm' : 'yyyy-MM-dd') : r[k]);
    return o;
  });
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function clean_(s, max) { return String(s == null ? '' : s).replace(/[\u0000-\u001f]/g, '').trim().slice(0, max || 40); }

function state_(ss, from, to) {
  const games = rows_(ss, 'games').filter(g => !g.deleted && (!from || g.date >= from) && (!to || g.date <= to));
  const ids = new Set(games.map(g => String(g.id)));
  const votes = rows_(ss, 'votes').filter(v => ids.has(String(v.gameId)));
  const lineups = rows_(ss, 'lineups').filter(l => ids.has(String(l.gameId)))
    .map(l => ({ gameId: l.gameId, lineup: JSON.parse(l.json || '[]'), by: l.by, ts: l.ts, ver: Number(l.ver) || 0 }));
  const roster = rows_(ss, 'roster').map(r => r.name);
  games.forEach(g => delete g._row); votes.forEach(v => delete v._row);
  return { ok: true, games, votes, lineups, roster, now: new Date().toISOString() };
}

function doGet(e) {
  const p = e.parameter || {};
  try {
    return out_(state_(book_(), p.from, p.to));
  } catch (err) {
    return out_({ ok: false, error: String(err) });
  }
}

function doPost(e) {
  let b;
  try { b = JSON.parse(e.postData.contents); } catch (err) { return out_({ ok: false, error: '잘못된 요청' }); }
  const code = PropertiesService.getScriptProperties().getProperty('PASSCODE');
  if (code && String(b.code || '') !== code) return out_({ ok: false, error: 'passcode' });

  const lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    const ss = book_();
    const now = new Date().toISOString();
    const sh = n => ss.getSheetByName(n);

    if (b.action === 'addGame') {
      const date = clean_(b.date, 10);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return out_({ ok: false, error: '날짜 형식' });
      const id = 'g' + Date.now().toString(36);
      sh('games').appendRow([id, date, clean_(b.time, 5), clean_(b.opp), clean_(b.league, 10), clean_(b.place), clean_(b.memo, 100), clean_(b.by), now, '']);
    }
    else if (b.action === 'deleteGame') {
      const g = rows_(ss, 'games').find(x => String(x.id) === String(b.gameId));
      if (g) sh('games').getRange(g._row, SHEETS.games.indexOf('deleted') + 1).setValue(now);
    }
    else if (b.action === 'vote') {
      const name = clean_(b.name), status = clean_(b.status, 4);
      if (!name || (status && STATUS.indexOf(status) < 0)) return out_({ ok: false, error: '투표 값' });
      const v = rows_(ss, 'votes').find(x => String(x.gameId) === String(b.gameId) && x.name === name);
      if (v && !status) sh('votes').deleteRow(v._row);                       // 투표 취소
      else if (v) sh('votes').getRange(v._row, 3, 1, 2).setValues([[status, now]]);
      else if (status) sh('votes').appendRow([clean_(b.gameId), name, status, now]);
    }
    else if (b.action === 'saveLineup') {
      const lineup = (Array.isArray(b.lineup) ? b.lineup : []).slice(0, 20)
        .map(x => ({ name: clean_(x.name), pos: clean_(x.pos, 4) }));
      const l = rows_(ss, 'lineups').find(x => String(x.gameId) === String(b.gameId));
      const ver = l ? Number(l.ver) || 0 : 0;
      // 다른 사람이 먼저 저장했으면 덮어쓰지 않고 알려줌
      if (Number(b.baseVer || 0) !== ver) return out_({ ok: false, error: 'conflict', state: state_(ss, b.from, b.to) });
      const row = [clean_(b.gameId), JSON.stringify(lineup), clean_(b.by), now, ver + 1];
      if (l) sh('lineups').getRange(l._row, 1, 1, row.length).setValues([row]);
      else sh('lineups').appendRow(row);
    }
    else if (b.action === 'addPlayer') {
      const name = clean_(b.name, 20);
      if (name && !rows_(ss, 'roster').some(r => r.name === name)) sh('roster').appendRow([name, now]);
    }
    else return out_({ ok: false, error: '알 수 없는 요청' });

    SpreadsheetApp.flush();
    return out_(state_(ss, b.from, b.to));
  } catch (err) {
    return out_({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}

/** 편집기에서 한 번 실행하면 시트가 만들어지고 권한 승인 창이 뜸 */
function setup() {
  const ss = book_();
  Logger.log('시트: ' + ss.getUrl());
}
