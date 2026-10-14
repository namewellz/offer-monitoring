$ErrorActionPreference = 'Stop'
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot"
$bt = "C:\Android\sdk\build-tools\34.0.0"
$decoded = "C:\Android\apktool\base_decoded"

# 1) network security config trusting user CAs
$xmlDir = "$decoded\res\xml"
New-Item -ItemType Directory -Path $xmlDir -Force | Out-Null
$nsc = @'
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="true">
        <trust-anchors>
            <certificates src="system" />
            <certificates src="user" />
        </trust-anchors>
    </base-config>
</network-security-config>
'@
Set-Content -Path "$xmlDir\network_security_config.xml" -Value $nsc -Encoding UTF8
Write-Output "wrote network_security_config.xml"

# 2) patch AndroidManifest
$mPath = "$decoded\AndroidManifest.xml"
$content = Get-Content $mPath -Raw
if ($content -notmatch "networkSecurityConfig") {
    $content = $content -replace '(<application )', '$1android:networkSecurityConfig="@xml/network_security_config" '
    Set-Content -Path $mPath -Value $content -Encoding UTF8 -NoNewline
    Write-Output "manifest patched"
} else {
    Write-Output "manifest already patched"
}
Select-String -Path $mPath -Pattern "networkSecurityConfig" | ForEach-Object { $_.Line.Substring(0, 200) }
