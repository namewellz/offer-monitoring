# Dump the BlueStacks instance configuration keys we need (root access, ABI, adb port).
$conf = 'C:\ProgramData\BlueStacks_nxt\bluestacks.conf'
if (-not (Test-Path $conf)) { Write-Output "bluestacks.conf ainda nao existe: $conf"; exit 0 }

Write-Output "== chaves relevantes =="
Get-Content $conf |
    Select-String -Pattern 'root|abi|arm|adb|installed_images|instance\.' |
    ForEach-Object { $_.Line } |
    Select-Object -First 80

Write-Output "`n== todas as imagens instaladas =="
Get-Content $conf | Select-String -Pattern 'installed_images' | ForEach-Object { $_.Line }

Write-Output "`n== portas adb =="
Get-Content $conf | Select-String -Pattern 'adb_port' | ForEach-Object { $_.Line }
