"""Patch the decoded Meu Atacadao APK so we can MITM it inside BlueStacks.

Three changes:
  1. root detection off  -> com/w3conext/jailbreak_root_detection/
       processJailBroken  -> success(false)
       processCheckIssues -> success(empty list)
  2. keep Firebase working after re-signing: force the X-Android-Cert header back
     to the original signing certificate SHA1 (otherwise FIS/Remote Config refuse
     the request and the app loses its whole configuration).
  3. trust our own CA: res/raw/mitm_ca.pem + res/xml/network_security_config.xml
     referenced from <application> in AndroidManifest.xml.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

SRC = Path(r"C:\Android\apktool\base_src")
MITM_CA = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
CERT_SHA1 = "97B1257A29CBA1049C4B1F2D4DE3BF"  # placeholder, replaced below
CERT_SHA1 = "97B1257A29CBA1049C4B1F2D4DE3DBE5B1262040"

JBR = SRC / "smali/com/w3conext/jailbreak_root_detection/JailbreakRootDetectionPlugin.smali"

NEW_JAIL_BROKEN = """\
.method private final processJailBroken(Luc/q;)V
    .locals 1

    sget-object v0, Ljava/lang/Boolean;->FALSE:Ljava/lang/Boolean;

    invoke-interface {p1, v0}, Luc/q;->success(Ljava/lang/Object;)V

    return-void
.end method"""

NEW_CHECK_ISSUES = """\
.method private final processCheckIssues(Luc/q;)V
    .locals 1

    new-instance v0, Ljava/util/ArrayList;

    invoke-direct {v0}, Ljava/util/ArrayList;-><init>()V

    invoke-interface {p1, v0}, Luc/q;->success(Ljava/lang/Object;)V

    return-void
.end method"""

NSC = """<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="true">
        <trust-anchors>
            <certificates src="system" />
            <certificates src="user" />
            <certificates src="@raw/mitm_ca" />
        </trust-anchors>
    </base-config>
</network-security-config>
"""


def replace_method(text: str, name: str, replacement: str) -> tuple[str, bool]:
    pattern = re.compile(rf"^\.method private final {name}\(Luc/q;\)V.*?^\.end method", re.S | re.M)
    if not pattern.search(text):
        return text, False
    return pattern.sub(replacement, text, count=1), True


def patch_root_detection() -> None:
    text = JBR.read_text(encoding="utf-8")
    text, ok1 = replace_method(text, "processJailBroken", NEW_JAIL_BROKEN)
    text, ok2 = replace_method(text, "processCheckIssues", NEW_CHECK_ISSUES)
    JBR.write_text(text, encoding="utf-8")
    print(f"  processJailBroken  patchado: {ok1}")
    print(f"  processCheckIssues patchado: {ok2}")


def patch_cert_headers() -> None:
    pattern = re.compile(
        r"(?P<indent>[ \t]*)const-string (?P<name>v\d+), \"X-Android-Cert\"[ \t]*\n"
        r"(?:[ \t]*\n)*[ \t]*invoke-\w+ \{(?P<regs>[^}]*)\}, Ljava/net/URLConnection;->"
        r"(?:setRequestProperty|addRequestProperty)"
    )
    touched = 0
    for path in SRC.joinpath("smali").rglob("*.smali"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "X-Android-Cert" not in text:
            continue

        def repl(match: re.Match[str]) -> str:
            regs = [r.strip() for r in match.group("regs").split(",")]
            value_reg = regs[-1]
            return (
                f"{match.group('indent')}const-string {value_reg}, \"{CERT_SHA1}\"\n" + match.group(0)
            )

        new_text, count = pattern.subn(repl, text)
        if count:
            path.write_text(new_text, encoding="utf-8")
            touched += count
            print(f"  {path.relative_to(SRC)}: {count} header(s)")
    print(f"  total de headers X-Android-Cert forcados: {touched}")


def patch_trust_store() -> None:
    raw = SRC / "res/raw"
    raw.mkdir(parents=True, exist_ok=True)
    shutil.copy(MITM_CA, raw / "mitm_ca.pem")

    xml = SRC / "res/xml"
    xml.mkdir(parents=True, exist_ok=True)
    (xml / "network_security_config.xml").write_text(NSC, encoding="utf-8")

    manifest = SRC / "AndroidManifest.xml"
    text = manifest.read_text(encoding="utf-8")
    if "networkSecurityConfig" in text:
        print("  manifest: ja tinha networkSecurityConfig")
        return
    new_text, count = re.subn(
        r"(<application\b)",
        r'\1 android:networkSecurityConfig="@xml/network_security_config"',
        text,
        count=1,
    )
    manifest.write_text(new_text, encoding="utf-8")
    print(f"  manifest: networkSecurityConfig inserido ({count})")


def fix_launch_background() -> None:
    """apktool turns the splash <bitmap> src into @null, which crashes MainActivity.

    Flutter's launch_background.xml only needs a valid layer-list, so use a
    framework colour and drop the broken bitmap items.
    """
    path = SRC / "res/drawable/launch_background.xml"
    if not path.exists():
        print("  launch_background.xml ausente")
        return
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<layer-list xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <item android:drawable="@android:color/white" />\n'
        "</layer-list>\n",
        encoding="utf-8",
    )
    print("  launch_background.xml corrigido (sem bitmap invalido)")


def main() -> None:
    if not SRC.exists():
        sys.exit(f"fonte decodificada ausente: {SRC}")
    print("== 1) deteccao de root desligada ==")
    patch_root_detection()
    print("== 2) X-Android-Cert forcado para o certificado original ==")
    patch_cert_headers()
    print("== 3) CA do mitmproxy embutida ==")
    patch_trust_store()
    print("== 4) splash do apktool corrigido ==")
    fix_launch_background()
    print("OK")


if __name__ == "__main__":
    main()
