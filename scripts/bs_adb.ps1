# Small helper: run a shell command inside the BlueStacks instance, reconnecting
# the adb link automatically (it drops often).
#
#   powershell -File scripts\bs_adb.ps1 -Cmd "id"
#   powershell -File scripts\bs_adb.ps1 -Root -Cmd "id"
param(
    [string]$Device = '127.0.0.1:5555',
    [string]$Cmd = 'id',
    [switch]$Root,
    [int]$Retries = 3
)

$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'

function Connect-Device {
    & $adb start-server 2>&1 | Out-Null
    for ($i = 0; $i -lt $Retries; $i++) {
        $list = & $adb devices 2>&1 | Out-String
        if ($list -match [regex]::Escape($Device)) { return $true }
        & $adb connect $Device 2>&1 | Out-Null
        Start-Sleep -Seconds 3
    }
    return $false
}

if (-not (Connect-Device)) { Write-Output "nao consegui conectar em $Device"; exit 1 }

if ($Root) {
    & $adb -s $Device root 2>&1 | Out-Null
    Start-Sleep -Seconds 6
    Connect-Device | Out-Null
}

& $adb -s $Device shell $Cmd
