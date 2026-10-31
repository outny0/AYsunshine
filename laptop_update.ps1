# AY션샤인 노트북 예약 작업 — 안양 포함 수집 → 검증(불일치면 중단) → data.json 커밋·push
# 작업 스케줄러 'AY션샤인_안양갱신'이 월 07:00 / 수 22:00 실행 (놓치면 켜진 뒤 바로)
# GitHub Actions(SKIP_ALB=1)도 data.json을 커밋하므로 항상 git pull 먼저, 충돌 나면 멈추고 로그만 남김
$repo = $PSScriptRoot
$git = 'C:\Program Files\Git\cmd\git.exe'
$python = 'C:\Users\a\AppData\Local\Programs\Python\Python312\python.exe'
$logDir = "$env:LOCALAPPDATA\AYsunshine\logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = "$logDir\update_$(Get-Date -Format 'yyMMdd_HHmm').log"

$env:PYTHONIOENCODING = 'utf-8'
Remove-Item Env:SKIP_ALB -ErrorAction SilentlyContinue
$env:GIT_TERMINAL_PROMPT = '0'       # 예약 실행 중엔 로그인 창을 띄우지 않고 실패로 끝냄
$env:GCM_INTERACTIVE = 'Never'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Set-Location $repo

function Log($msg) { "$(Get-Date -Format 'HH:mm:ss') $msg" | Add-Content $log -Encoding UTF8 }
function Run($name, $exe, [string[]]$argv) {
    $out = & $exe @argv 2>&1 | ForEach-Object { "$_" } | Out-String
    $code = $LASTEXITCODE
    $out.TrimEnd() | Add-Content $log -Encoding UTF8
    Log "[$name] exit=$code"
    return $code
}
function Stop-Run($msg) { Log "중단: $msg"; exit 1 }

Log "시작 ($repo)"

# 노트북이 막 켜졌을 때 네트워크가 늦게 잡힐 수 있음 — 최대 5분 대기
for ($i = 0; $i -lt 30; $i++) {
    if (Test-NetConnection github.com -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue) { break }
    Start-Sleep 10
}

if ((Run 'pull' $git @('pull', '--ff-only')) -ne 0) { Stop-Run 'git pull 실패(충돌·로컬 변경 확인 필요)' }
if ((Run 'scrape' $python @('scrape_leagues.py')) -ne 0) { Stop-Run '수집 실패' }
if ((Run 'validate' $python @('validate_scrape.py')) -ne 0) { Stop-Run '검증 불일치 — data.json 그대로 둠' }

Copy-Item -LiteralPath "$repo\data_scraped.json" -Destination "$repo\data.json" -Force
# 'updated' 시각만 바뀐 경우는 커밋하지 않음 (Actions와 같은 기준)
& $git diff --quiet -I '"updated"' -- data.json
if ($LASTEXITCODE -eq 0) {
    & $git checkout -- data.json
    Log '변경 없음'; exit 0
}

$msgFile = "$logDir\commit_msg.txt"
[IO.File]::WriteAllText($msgFile, "data: 안양 포함 리그 기록 갱신 (노트북) $(Get-Date -Format 'yyyy-MM-dd HH:mm')", (New-Object Text.UTF8Encoding $false))
if ((Run 'commit' $git @('commit', '-F', $msgFile, '--', 'data.json')) -ne 0) { Stop-Run '커밋 실패' }

# 수집하는 사이 Actions가 커밋했을 수 있음 — 다시 받아서 위에 얹기, 충돌이면 되돌리고 멈춤
if ((Run 'pull-rebase' $git @('pull', '--rebase')) -ne 0) {
    Run 'rebase-abort' $git @('rebase', '--abort') | Out-Null
    Stop-Run 'data.json 충돌 — 로컬 커밋은 남겨둠, 직접 확인 필요'
}
if ((Run 'push' $git @('push')) -ne 0) { Stop-Run 'push 실패(로그인 만료 등)' }
Log '끝'
