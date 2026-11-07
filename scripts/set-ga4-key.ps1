# GA4 サービスアカウント鍵（JSON）を GitHub Secrets に登録する。
# ファイル選択画面で鍵を選ぶだけ。鍵の中身は画面にもログにも出さない。
Add-Type -AssemblyName System.Windows.Forms
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.Title = "ダウンロードしたサービスアカウントの鍵（.json）を選んでください"
$dlg.Filter = "JSON (*.json)|*.json"
$dlg.InitialDirectory = [Environment]::GetFolderPath("UserProfile") + "\Downloads"
if ($dlg.ShowDialog() -ne "OK") { Write-Host "キャンセルしました"; exit 1 }

$json = Get-Content -Raw -Encoding utf8 $dlg.FileName
try { $obj = $json | ConvertFrom-Json } catch { Write-Host "JSON として読めませんでした。ファイルを確認してください"; exit 1 }
if ($obj.type -ne "service_account") { Write-Host "サービスアカウントの鍵ではないようです（type が service_account ではありません）"; exit 1 }

$json | & 'C:\Program Files\GitHub CLI\gh.exe' secret set GA4_SA_KEY -R phaedla0305-oss/affiliate-team
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "登録しました。サービスアカウントのメールアドレス（GA4 で閲覧権限を付ける相手）:"
    Write-Host "  $($obj.client_email)"
    Write-Host ""
    Write-Host "安全のため、ダウンロードした鍵ファイルは削除してください: $($dlg.FileName)"
}
