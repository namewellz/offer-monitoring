$ErrorActionPreference = 'Stop'
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot"
$java = "$env:JAVA_HOME\bin\java.exe"
$bt = "C:\Android\sdk\build-tools\34.0.0"
$decoded = "C:\Android\apktool\base_decoded"
$out = "C:\Android\apktool\modded"
$ks = "C:\Android\apktool\debug.keystore"

# fresh decode
if (Test-Path $decoded) { Remove-Item -Recurse -Force $decoded }
& $java -jar "C:\Android\apktool\apktool.jar" d -f -s -o $decoded "C:\Users\Wellz\AppData\Local\Temp\atacadao-xapk\base.apk" 2>&1 | Select-Object -Last 2

# 1) embed the mitmproxy CA as a raw resource
$rawDir = "$decoded\res\raw"
New-Item -ItemType Directory -Path $rawDir -Force | Out-Null
Copy-Item "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.pem" "$rawDir\mitm_ca.pem" -Force
Write-Output "embedded CA: $(Test-Path "$rawDir\mitm_ca.pem")"

# 2) network security config trusting system + the embedded CA
$xmlDir = "$decoded\res\xml"
New-Item -ItemType Directory -Path $xmlDir -Force | Out-Null
$nsc = @'
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="true">
        <trust-anchors>
            <certificates src="system" />
            <certificates src="@raw/mitm_ca" />
            <certificates src="user" />
        </trust-anchors>
    </base-config>
</network-security-config>
'@
Set-Content -Path "$xmlDir\network_security_config.xml" -Value $nsc -Encoding UTF8

# 3) manifest patch
$mPath = "$decoded\AndroidManifest.xml"
$content = Get-Content $mPath -Raw
$content = $content -replace '(<application )', '$1android:networkSecurityConfig="@xml/network_security_config" '
Set-Content -Path $mPath -Value $content -Encoding UTF8 -NoNewline
Write-Output "manifest patched: $($content -match 'networkSecurityConfig')"

# 4) build
& $java -jar "C:\Android\apktool\apktool.jar" b $decoded -o "$out\base_mod.apk" 2>&1 | Select-Object -Last 3

# 5) sign all
Copy-Item "$env:TEMP\atacadao-xapk\split_0.apk" "$out\split_0.apk" -Force
Copy-Item "$env:TEMP\atacadao-xapk\split_1.apk" "$out\split_1.apk" -Force
Copy-Item "$env:TEMP\atacadao-xapk\split_2.apk" "$out\split_2.apk" -Force
Copy-Item "$env:TEMP\atacadao-xapk\split_3.apk" "$out\split_3.apk" -Force
foreach ($apk in @("base_mod.apk", "split_0.apk", "split_1.apk", "split_2.apk", "split_3.apk")) {
    $p = "$out\$apk"; $a = "$out\al_$apk"
    & "$bt\zipalign.exe" -f 4 $p $a 2>&1 | Out-Null
    & "$bt\apksigner.bat" sign --ks $ks --ks-pass pass:android --key-pass pass:android --ks-key-alias androiddebugkey $a 2>&1 | Out-Null
    Remove-Item $p -Force; Move-Item $a $p
}
Get-ChildItem $out -Filter *.apk | Select-Object Name, @{N='MB';E={[math]::Round($_.Length/1MB,1)}} | Format-Table -AutoSize
Write-Output "DONE"
