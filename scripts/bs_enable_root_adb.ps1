# Enable ADB + root access for the BlueStacks instance (must run elevated, with
# BlueStacks closed so it does not overwrite bluestacks.conf on exit).
$ErrorActionPreference = 'Continue'
$log = 'C:\Android\bs\enable-root-transcript.txt'
Remove-Item $log -Force -ErrorAction SilentlyContinue
Start-Transcript -Path $log -Force | Out-Null

$conf = 'C:\ProgramData\BlueStacks_nxt\bluestacks.conf'
Write-Output "elevated: $((New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"

Write-Output '== parando BlueStacks =='
Get-Process | Where-Object { $_.ProcessName -match 'HD-Player|BlueStacks|Bstk' } |
    ForEach-Object { Write-Output "  kill $($_.ProcessName) ($($_.Id))"; Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 8

if (-not (Test-Path $conf)) { Write-Output "conf ausente: $conf"; Stop-Transcript; exit 1 }
Copy-Item $conf "$conf.bak-$(Get-Date -Format yyyyMMdd-HHmmss)" -Force

$text = Get-Content $conf -Raw
$changes = @{
    'bst\.enable_adb_access="\d+"'                     = 'bst.enable_adb_access="1"'
    'bst\.enable_adb_remote_access="\d+"'              = 'bst.enable_adb_remote_access="1"'
    'bst\.feature\.rooting="\d+"'                      = 'bst.feature.rooting="1"'
    'bst\.instance\.Pie64\.enable_root_access="\d+"'   = 'bst.instance.Pie64.enable_root_access="1"'
}
foreach ($pattern in $changes.Keys) {
    $before = ([regex]::Matches($text, $pattern)).Count
    $text = [regex]::Replace($text, $pattern, $changes[$pattern])
    Write-Output "  $pattern -> $($changes[$pattern]) (ocorrencias: $before)"
}
Set-Content -Path $conf -Value $text -NoNewline -Encoding UTF8

Write-Output '== valores resultantes =='
Get-Content $conf | Select-String -Pattern 'enable_adb|rooting|enable_root_access|abi_list|adb_port' | ForEach-Object { $_.Line }

Write-Output '== subindo BlueStacks =='
$player = 'C:\Program Files\BlueStacks_nxt\HD-Player.exe'
if (Test-Path $player) {
    Start-Process -FilePath $player -ArgumentList '--instance', 'Pie64'
    Write-Output 'HD-Player iniciado (Pie64)'
} else {
    Write-Output "nao encontrei $player"
    Get-ChildItem 'C:\Program Files\BlueStacks_nxt' -Filter '*.exe' | Select-Object Name | Format-Table -AutoSize | Out-String | Write-Output
}

Stop-Transcript | Out-Null
