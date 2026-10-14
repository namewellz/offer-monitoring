$ErrorActionPreference = 'Continue'
$log = 'C:\Android\bs\install-transcript.txt'
Remove-Item $log -Force -ErrorAction SilentlyContinue
Start-Transcript -Path $log -Force | Out-Null

Write-Output "identity: $([Security.Principal.WindowsIdentity]::GetCurrent().Name)"
Write-Output "elevated: $((New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"

$exe = 'C:\Android\bs\BlueStacksMicroInstaller.exe'
if (-not (Test-Path $exe)) { Write-Output "instalador ausente: $exe"; Stop-Transcript; exit 1 }

Write-Output "== iniciando instalação silenciosa =="
$proc = Start-Process -FilePath $exe -ArgumentList '/S' -PassThru
Write-Output "pid=$($proc.Id)"
$deadline = (Get-Date).AddMinutes(25)
while (-not $proc.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 10 }
Write-Output "terminou: $($proc.HasExited) exit=$($proc.ExitCode)"

Write-Output "== Program Files\BlueStacks_nxt =="
Get-ChildItem 'C:\Program Files\BlueStacks_nxt' -ErrorAction SilentlyContinue |
    Select-Object Name, Length | Format-Table -AutoSize | Out-String | Write-Output

Write-Output "== ProgramData\BlueStacks_nxt =="
Get-ChildItem 'C:\ProgramData\BlueStacks_nxt' -ErrorAction SilentlyContinue |
    Select-Object Name, Length | Format-Table -AutoSize | Out-String | Write-Output

Stop-Transcript | Out-Null
