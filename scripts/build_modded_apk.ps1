$ErrorActionPreference = 'Continue'
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot"
$java = "$env:JAVA_HOME\bin\java.exe"
$bt = "C:\Android\sdk\build-tools\34.0.0"
$ks = "C:\Android\apktool\debug.keystore"
$out = "C:\Android\apktool\modded"
New-Item -ItemType Directory -Path $out -Force | Out-Null

# 1) build
Write-Output "=== apktool build ==="
& $java -jar "C:\Android\apktool\apktool.jar" b "C:\Android\apktool\base_decoded" -o "$out\base_mod.apk" 2>&1 | Select-Object -Last 8
Write-Output "base_mod exists: $(Test-Path "$out\base_mod.apk")"

# 2) keystore
if (-not (Test-Path $ks)) {
    Write-Output "=== creating keystore ==="
    & "$env:JAVA_HOME\bin\keytool.exe" -genkeypair -v -keystore $ks -storepass android -keypass android -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US" 2>&1 | Select-Object -Last 3
}

# 3) copy splits and sign all with same key
$src = "$env:TEMP\atacadao-xapk"
Copy-Item "$src\split_0.apk" "$out\split_0.apk" -Force
Copy-Item "$src\split_1.apk" "$out\split_1.apk" -Force
Copy-Item "$src\split_2.apk" "$out\split_2.apk" -Force
Copy-Item "$src\split_3.apk" "$out\split_3.apk" -Force

foreach ($apk in @("base_mod.apk", "split_0.apk", "split_1.apk", "split_2.apk", "split_3.apk")) {
    $p = "$out\$apk"
    $aligned = "$out\aligned_$apk"
    & "$bt\zipalign.exe" -f 4 $p $aligned 2>&1 | Out-Null
    & "$bt\apksigner.bat" sign --ks $ks --ks-pass pass:android --key-pass pass:android --ks-key-alias androiddebugkey $aligned 2>&1 | Select-Object -Last 2
    Remove-Item $p -Force
    Move-Item $aligned $p
    $v = & "$bt\apksigner.bat" verify $p 2>&1
    Write-Output "$apk signed: $([string]::IsNullOrEmpty(($v | Where-Object { $_ -match 'DOES NOT VERIFY|ERROR' })))"
}
Get-ChildItem $out -Filter *.apk | Select-Object Name, @{N='MB';E={[math]::Round($_.Length/1MB,1)}} | Format-Table -AutoSize
