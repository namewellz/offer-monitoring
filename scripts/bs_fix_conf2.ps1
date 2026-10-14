# Repair bluestacks.conf properly.
# Previous attempt corrupted it: File.ReadAllText(..., Encoding.UTF8) already strips the
# BOM, and the extra StartsWith(FEFF) strip removed the leading "b" of "bst.ai.enabled".
$ErrorActionPreference = 'Continue'
$log = 'C:\Android\bs\fix-conf2-transcript.txt'
Remove-Item $log -Force -ErrorAction SilentlyContinue
Start-Transcript -Path $log -Force | Out-Null

$conf = 'C:\ProgramData\BlueStacks_nxt\bluestacks.conf'
$dir = Split-Path $conf

Write-Output '== parando BlueStacks =='
Get-Process | Where-Object { $_.ProcessName -match 'HD-Player|BlueStacks|Bstk' } |
    ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 6

$backup = Get-ChildItem "$dir\bluestacks.conf.bak-*" | Sort-Object LastWriteTime | Select-Object -First 1
Write-Output "backup mais antigo (pristino): $($backup.FullName)"

# read bytes, strip a UTF-8 BOM once, decode
$bytes = [IO.File]::ReadAllBytes($backup.FullName)
$offset = 0
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { $offset = 3 }
$text = [Text.Encoding]::UTF8.GetString($bytes, $offset, $bytes.Length - $offset)
Write-Output ("comeca com: {0}" -f $text.Substring(0, [Math]::Min(40, $text.Length)).Replace("`r", ' ').Replace("`n", ' '))

$changes = @{
    'bst\.enable_adb_access="\d+"'                   = 'bst.enable_adb_access="1"'
    'bst\.enable_adb_remote_access="\d+"'            = 'bst.enable_adb_remote_access="1"'
    'bst\.feature\.rooting="\d+"'                    = 'bst.feature.rooting="1"'
    'bst\.instance\.Pie64\.enable_root_access="\d+"' = 'bst.instance.Pie64.enable_root_access="1"'
}
foreach ($pattern in $changes.Keys) { $text = [regex]::Replace($text, $pattern, $changes[$pattern]) }

$utf8NoBom = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($conf, $text, $utf8NoBom)

$check = [IO.File]::ReadAllBytes($conf)
Write-Output ("novo comeco: {0}" -f (($check[0..15] | ForEach-Object { $_ }) | ForEach-Object { [char]$_ }) -join '')
Write-Output ("linhas: {0}" -f (Get-Content $conf).Count)
Write-Output '== valores =='
Get-Content $conf | Select-String -Pattern 'enable_adb|rooting|enable_root_access|abi_list|adb_port' | ForEach-Object { $_.Line }

Write-Output '== subindo BlueStacks =='
Start-Process -FilePath 'C:\Program Files\BlueStacks_nxt\HD-Player.exe' -ArgumentList '--instance', 'Pie64'
Start-Sleep -Seconds 45
Get-Process | Where-Object { $_.ProcessName -match 'HD-Player' } | Select-Object ProcessName, Id, MainWindowTitle | Format-Table -AutoSize | Out-String | Write-Output

Stop-Transcript | Out-Null
