# Repair bluestacks.conf: the previous edit wrote a UTF-8 BOM (PowerShell 5.1
# Set-Content -Encoding UTF8), which BlueStacks' parser rejects. Restore the
# backup and re-apply the changes as UTF-8 *without* BOM.
$ErrorActionPreference = 'Continue'
$log = 'C:\Android\bs\fix-conf-transcript.txt'
Remove-Item $log -Force -ErrorAction SilentlyContinue
Start-Transcript -Path $log -Force | Out-Null

$conf = 'C:\ProgramData\BlueStacks_nxt\bluestacks.conf'
$dir = Split-Path $conf

Write-Output '== parando BlueStacks =='
Get-Process | Where-Object { $_.ProcessName -match 'HD-Player|BlueStacks|Bstk' } |
    ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 6

Write-Output '== estado atual =='
$bytes = [IO.File]::ReadAllBytes($conf)
Write-Output ("primeiros bytes: {0}" -f (($bytes[0..3] | ForEach-Object { $_.ToString('X2') }) -join ' '))
Write-Output ("tem BOM: {0}" -f ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF))

$backup = Get-ChildItem "$dir\bluestacks.conf.bak-*" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $backup) {
    Write-Output 'nenhum backup encontrado - vou apenas remover o BOM do arquivo atual'
    $text = [Text.Encoding]::UTF8.GetString($bytes)
    if ($text.StartsWith([char]0xFEFF)) { $text = $text.Substring(1) }
} else {
    Write-Output "restaurando backup: $($backup.Name)"
    $text = [IO.File]::ReadAllText($backup.FullName, [Text.Encoding]::UTF8)
    if ($text.StartsWith([char]0xFEFF)) { $text = $text.Substring(1) }
}

$changes = @{
    'bst\.enable_adb_access="\d+"'                   = 'bst.enable_adb_access="1"'
    'bst\.enable_adb_remote_access="\d+"'            = 'bst.enable_adb_remote_access="1"'
    'bst\.feature\.rooting="\d+"'                    = 'bst.feature.rooting="1"'
    'bst\.instance\.Pie64\.enable_root_access="\d+"' = 'bst.instance.Pie64.enable_root_access="1"'
}
foreach ($pattern in $changes.Keys) {
    $text = [regex]::Replace($text, $pattern, $changes[$pattern])
}

$utf8NoBom = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($conf, $text, $utf8NoBom)

$bytes2 = [IO.File]::ReadAllBytes($conf)
Write-Output ("novos primeiros bytes: {0}" -f (($bytes2[0..3] | ForEach-Object { $_.ToString('X2') }) -join ' '))
Write-Output '== valores =='
Get-Content $conf | Select-String -Pattern 'enable_adb|rooting|enable_root_access|abi_list|adb_port' | ForEach-Object { $_.Line }

Write-Output '== subindo BlueStacks =='
Start-Process -FilePath 'C:\Program Files\BlueStacks_nxt\HD-Player.exe' -ArgumentList '--instance', 'Pie64'
Start-Sleep -Seconds 30
Get-Process | Where-Object { $_.ProcessName -match 'HD-Player|BlueStacks' } | Select-Object ProcessName, Id | Format-Table -AutoSize | Out-String | Write-Output

Stop-Transcript | Out-Null
