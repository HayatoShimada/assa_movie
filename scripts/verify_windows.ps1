# Windowsのインストーラを実機で検証する。
#
# CIでビルドが通ることと、インストールしたアプリが起動することは別問題だった
# (v0.9.2は3OSぶんのインストーラが出来ていたが、Windows版は起動できなかった)。
# ここでは「入れて・起動して・閉じる」までを実際にやって確かめる。
#
#   ./scripts/verify_windows.ps1 -Installer path\to\KirinukiStudio_x64-setup.exe
#   ./scripts/verify_windows.ps1            # インストール済みのものをそのまま検証
#
# 終了コード 0 = 全項目OK。CIのwindowsランナーでもそのまま回せる。
[CmdletBinding()]
param(
    # NSISインストーラ。省略するとインストール手順を飛ばす
    [string]$Installer,
    # ウィンドウが出るまで待つ上限(初回はDB作成があるので長め)
    [int]$ReadyTimeoutSec = 90,
    # ログの採取先
    [string]$OutDir = "$env:TEMP\ks-verify"
)

$ErrorActionPreference = "Stop"
$InstallDir = "$env:LOCALAPPDATA\KirinukiStudio"
$AppExe = "$InstallDir\kirinuki-studio.exe"
$LogDir = "$env:APPDATA\kirinuki-studio\logs"

$script:Failures = @()

function Step($name) { Write-Host "`n=== $name ===" -ForegroundColor Cyan }
function Ok($msg) { Write-Host "  OK   $msg" -ForegroundColor Green }
function Ng($msg) { Write-Host "  NG   $msg" -ForegroundColor Red; $script:Failures += $msg }
function Info($msg) { Write-Host "       $msg" -ForegroundColor DarkGray }

New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

# ---- 1. インストール ----------------------------------------------------
if ($Installer) {
    Step "1. インストール"
    if (-not (Test-Path $Installer)) { throw "インストーラが見つかりません: $Installer" }
    $sig = (Get-AuthenticodeSignature $Installer).Status
    if ($sig -eq "Valid") { Ok "署名: $sig" } else { Info "署名: $sig (SmartScreenの警告が出ます)" }

    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath $Installer -ArgumentList "/S" -Wait -PassThru
    $sw.Stop()
    if ($p.ExitCode -eq 0) {
        Ok "サイレントインストール完了 ($([int]$sw.Elapsed.TotalSeconds)秒)"
    } else {
        Ng "インストーラが異常終了 ExitCode=$($p.ExitCode)"
    }
} else {
    Step "1. インストール (スキップ: -Installer 未指定)"
}

# ---- 2. 配置の確認 ------------------------------------------------------
Step "2. 配置されたファイル"
if (Test-Path $AppExe) { Ok "アプリ本体: kirinuki-studio.exe" } else { Ng "アプリ本体が無い: $AppExe" }

# Tauriはサイドカーを .exe 付きで配置する。Rust側の探索名と一致していないと
# 「同梱バックエンドが無い」と判定され、開発用のuvフォールバックに落ちて即死する
$sidecar = "$InstallDir\kirinuki-studio-backend.exe"
if (Test-Path $sidecar) { Ok "同梱バックエンド: $([int]((Get-Item $sidecar).Length / 1MB))MB" } else { Ng "同梱バックエンドが無い: $sidecar" }

# 同梱物は tauri.windows.conf.json の resources と1対1で対応する。
# 「同梱したつもり」を防ぐため、実パスで並べて確かめる。
# ライセンス表記は再配布の条件そのものなので、欠けたら配ってはいけない
$bundled = @(
    "bin\ffmpeg.exe", "bin\ffprobe.exe", "bin\whisper-cli.exe",
    "models\sherpa-onnx-pyannote-segmentation-3-0\model.onnx",
    "models\speaker-embedding.onnx",
    "licenses\ffmpeg\LICENSE.txt", "licenses\ffmpeg\NOTICE.md",
    "licenses\ffmpeg\THIRD-PARTY-NOTICES.txt", "licenses\ffmpeg\VERSION.txt",
    "licenses\whispercpp\LICENSE.txt", "licenses\whispercpp\VERSION.txt",
    "licenses\diarization\LICENSE-segmentation.txt",
    "licenses\diarization\LICENSE-embedding-Apache-2.0.txt",
    "licenses\diarization\NOTICE.md",
    "licenses\python\THIRD-PARTY-NOTICES.txt"
)
foreach ($rel in $bundled) {
    $path = Join-Path $InstallDir $rel
    if (Test-Path $path) {
        Ok "同梱: $rel ($([int]((Get-Item $path).Length / 1KB))KB)"
    } else {
        Ng "同梱物が無い: $rel"
    }
}

Get-ChildItem $InstallDir -ErrorAction SilentlyContinue |
    Select-Object Name, Length | Format-Table -AutoSize | Out-String -Width 100 | Write-Host

$reg = Get-ItemProperty "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -like "*irinuki*" }
if ($reg) { Ok "アンインストール登録: $($reg.DisplayName) $($reg.DisplayVersion)" } else { Ng "アンインストール登録が無い" }

# ---- 3. 起動 ------------------------------------------------------------
Step "3. 起動"
Get-Process -Name "kirinuki-studio*" -ErrorAction SilentlyContinue | Stop-Process -Force
if (Test-Path $LogDir) { Get-ChildItem $LogDir -Filter "*.log" | Remove-Item -Force -ErrorAction SilentlyContinue }

$appOut = "$OutDir\app-stdout.log"
$appErr = "$OutDir\app-stderr.log"
$app = Start-Process $AppExe -PassThru -RedirectStandardOutput $appOut -RedirectStandardError $appErr

$deadline = (Get-Date).AddSeconds($ReadyTimeoutSec)
$windowTitle = ""
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    if ($app.HasExited) { break }
    $windowTitle = (Get-Process -Id $app.Id).MainWindowTitle
    if ($windowTitle) { break }
}

if ($app.HasExited) {
    # v0.9.2のWindows版はここで落ちていた(0.06秒でexit 1)。この判定が本丸
    Ng "アプリが起動せずに終了した (ExitCode=$($app.ExitCode))"
} elseif ($windowTitle) {
    Ok "ウィンドウが開いた: '$windowTitle'"
} else {
    # ウィンドウの生成はデスクトップセッションの有無に左右される(CIのランナーなど)。
    # プロセスが生きていてAPIが応答するなら、起動そのものは成立している。
    # 「即終了する」退行は上の分岐で捕まえられるので、ここは警告に留める
    Info "$ReadyTimeoutSec 秒たってもウィンドウが出ない(プロセスは生存中)"
    Info "デスクトップセッションが無い環境ではここは出ない。下の疎通確認で判断する"
}

# ---- 4. バックエンドの疎通 ----------------------------------------------
Step "4. バックエンドの疎通"
if (-not $app.HasExited) {
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($app.Id)"
    $be = $children | Where-Object { $_.Name -like "*backend*" }
    if ($be) { Ok "バックエンドの子プロセスが動いている (PID=$($be.ProcessId -join ','))" } else { Ng "バックエンドの子プロセスが無い" }

    # シェルがログに書いたAPIのURLを拾って直接叩く(ポートは起動ごとに変わるため)。
    # ウィンドウが出ない環境ではここが唯一の「本当に動いている」証拠になるので、
    # 起動待ちの上限まで粘る
    $shellLog = "$LogDir\shell.log"
    $base = $null
    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSec)
    while (-not $base -and (Get-Date) -lt $deadline) {
        if (Test-Path $shellLog) {
            $m = Select-String -Path $shellLog -Pattern 'http://127\.0\.0\.1:\d+' -Encoding utf8 |
                Select-Object -Last 1
            if ($m) { $base = $m.Matches[0].Value; break }
        }
        if ($app.HasExited) { break }
        Start-Sleep -Milliseconds 500
    }

    # PyInstallerのonefileは実行時に %TEMP%\_MEI* へ展開する。ここに必要な
    # データが入っていないと、起動は通るのに処理の途中で落ちる。
    # v0.9.3は faster-whisper のVADモデルが入っておらず、文字起こしが必ず
    # NO_SUCHFILE で止まった(起動確認だけでは見つけられなかった)
    $required = @("faster_whisper\assets\*.onnx")
    foreach ($pattern in $required) {
        $hit = Get-ChildItem "$env:TEMP\_MEI*\$pattern" -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($hit) { Ok "同梱データ: $pattern" } else { Ng "同梱データが無い: $pattern" }
    }

    if (-not $base) {
        Ng "shell.log にAPIのURLが出てこない(バックエンドが起動していない)"
    } else {
        try {
            $r = Invoke-WebRequest "$base/api/health" -UseBasicParsing -TimeoutSec 10
            Ok "GET $base/api/health => $($r.StatusCode) $($r.Content)"
        } catch {
            Ng "health が叩けない: $_"
        }

        # ---- 同梱物が「使えるか」をバックエンドに解決させる ----
        #
        # ファイルの存在検査では足りない。v0.9.6はwhisper.cppを同梱したのに
        # エンジン選択がそれを選ばず、同梱した意味がまったく無かった。
        # 探索と選択はバックエンドが持っているので、そこに聞く
        try {
            $setup = Invoke-RestMethod "$base/api/setup" -TimeoutSec 15
            if ($setup.diarization.ready) {
                Ok "話者分離モデルが使える(同梱物から解決できている)"
            } else {
                Ng "話者分離が未準備: $($setup.diarization.note)"
            }
            if ($setup.whispercpp.installable) {
                Ok "whisper.cpp 本体を見つけている"
            } else {
                Ng "whisper.cpp 本体が見つからない: $($setup.whispercpp.note)"
            }
        } catch {
            Ng "/api/setup が叩けない: $_"
        }

        try {
            # 環境スキャンはGPU検出に子プロセスを使うので少し待つ
            $env_ = Invoke-RestMethod "$base/api/environment" -TimeoutSec 60
            $gpu = if ($env_.gpu.name) { $env_.gpu.name } else { "(検出なし)" }
            Info "GPU: $gpu / accel: $($env_.accel)"
            Info "推奨ASR: $($env_.recommendations.asr_engine) / $($env_.recommendations.asr_model)"

            if ($env_.ffmpeg) { Ok "ffmpeg を見つけている" } else { Ng "ffmpeg が見つからない" }
            if ($env_.encoder) { Ok "動画エンコーダ: $($env_.encoder)" } else { Ng "エンコーダを決められない" }

            # GPUが載っているのにwhisper.cppが選ばれないなら、同梱した意味がない
            if ($env_.gpu.name -and $env_.recommendations.asr_engine -ne "whispercpp") {
                Ng "GPUがあるのに推奨が $($env_.recommendations.asr_engine)(同梱のwhisper.cppが選ばれていない)"
            }
        } catch {
            Ng "/api/environment が叩けない: $_"
        }
    }
} else {
    Info "アプリが落ちているので疎通確認はスキップ"
}

# ---- 5. 終了と後始末 ----------------------------------------------------
Step "5. 終了時にプロセスが残らないか"
if (-not $app.HasExited) {
    # ×ボタン相当。Stop-Process(強制終了)ではDropが走らず後始末の検証にならない
    [void](Get-Process -Id $app.Id).CloseMainWindow()
    $app.WaitForExit(15000) | Out-Null
}
Start-Sleep -Seconds 3
$orphans = @(Get-Process -Name "kirinuki-studio-backend" -ErrorAction SilentlyContinue)
if ($orphans.Count -eq 0) {
    Ok "残留プロセスなし"
} else {
    Ng "バックエンドが $($orphans.Count) 件残っている (PID=$($orphans.Id -join ','))"
    $orphans | Stop-Process -Force
}

# ---- 6. ログの採取 ------------------------------------------------------
Step "6. ログ"
if (Test-Path $LogDir) { Copy-Item "$LogDir\*.log" $OutDir -Force -ErrorAction SilentlyContinue }
foreach ($f in (Get-ChildItem $OutDir -Filter "*.log" | Sort-Object Name)) {
    # ログはUTF-8。指定しないとcp932として読まれて日本語が化ける
    $body = Get-Content $f.FullName -Tail 25 -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($body) {
        Write-Host "`n--- $($f.Name) (末尾25行) ---" -ForegroundColor Yellow
        $body | ForEach-Object { Write-Host "  $_" }
    }
}
Info "採取先: $OutDir"

# ---- まとめ -------------------------------------------------------------
Write-Host ""
if ($script:Failures.Count -eq 0) {
    Write-Host "=== すべてOK ===" -ForegroundColor Green
    exit 0
} else {
    Write-Host "=== $($script:Failures.Count) 件のNG ===" -ForegroundColor Red
    $script:Failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
