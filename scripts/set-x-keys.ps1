# X（旧Twitter）の API キー4つを GitHub Secrets に登録する。
# 入力した文字は画面に表示されず、ログにも残らない。
param([string[]]$Only)
$repo = "phaedla0305-oss/zaitaku-toolbox"
$gh = 'C:\Program Files\GitHub CLI\gh.exe'
$items = @(
    @{ Name = "X_API_KEY";       Label = "API Key（Consumer Key）" },
    @{ Name = "X_API_SECRET";    Label = "API Key Secret（Consumer Secret）" },
    @{ Name = "X_ACCESS_TOKEN";  Label = "Access Token" },
    @{ Name = "X_ACCESS_SECRET"; Label = "Access Token Secret" }
)
Write-Host "X 開発者ポータルの「Keys and tokens」から、表示された順にコピーして貼り付けてください。"
Write-Host "（貼り付けても画面には何も表示されません。貼り付けたら Enter）"
Write-Host ""
if ($Only) {
    $names = $Only -join "," -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    $items = @($items | Where-Object { $names -contains $_.Name })
}
if ($items.Count -eq 0) { Write-Host "登録する項目が見つかりません。中止しました"; exit 1 }
foreach ($it in $items) {
    $plain = ""
    for ($try = 1; $try -le 5 -and [string]::IsNullOrWhiteSpace($plain); $try++) {
        $sec = Read-Host -AsSecureString "$($it.Label) を貼り付け"
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
        if ([string]::IsNullOrWhiteSpace($plain)) { Write-Host "  空でした（コピーに改行が含まれていた可能性があります）。もう一度貼り付けてください。" }
    }
    if ([string]::IsNullOrWhiteSpace($plain)) { Write-Host "入力がないため中止しました"; exit 1 }
    $plain.Trim() | & $gh secret set $it.Name -R $repo
    if ($LASTEXITCODE -ne 0) { Write-Host "$($it.Name) の登録に失敗しました"; exit 1 }
    $plain = $null
}
Write-Host ""
Write-Host ("登録しました（" + (($items | ForEach-Object { $_.Name }) -join ", ") + "）。チャットに戻って「登録完了」と送ってください。")
