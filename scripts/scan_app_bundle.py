"""Scan a Capacitor/Cordova/WebView app bundle (or any JS/HTML asset tree) for endpoints.

Hybrid apps (Ionic/Angular/React inside a WebView) ship the whole frontend as
readable JavaScript, so the API contract — base URLs, route templates, query
parameter names and even embedded credentials — is in plain text. This is by far
the cheapest first step when reverse engineering that kind of app.

Usage
-----
    python scripts/scan_app_bundle.py "C:\\Android\\apktool\\spani_src\\assets"
    python scripts/scan_app_bundle.py <dir> --filter spani --show-routes
    python scripts/scan_app_bundle.py <dir> --json out.json

What it reports
---------------
* every distinct host seen in absolute URLs (with the path prefixes used)
* route-looking string literals (``/api/v1/...``, ``/v2/...``)
* config-looking keys next to a URL (``apiUrl``, ``baseUrl``, ``clientId``,
  ``token``, ``secret``, ``apiKey`` …)
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

TEXT_SUFFIXES = {".js", ".mjs", ".cjs", ".html", ".htm", ".json", ".css", ".map", ".txt", ".xml"}

URL_RE = re.compile(r"https?://[a-zA-Z0-9][a-zA-Z0-9._~:/?#\[\]@!$&'()*+,;=%-]*")
# Routes live in plain strings and in template literals, so backticks matter:
# the VIPCommerce bundle builds them as `/loja/filiais/${id}`.
ROUTE_RE = re.compile(r"[\"'`](/[a-zA-Z0-9][a-zA-Z0-9_\-./{}$:]{2,80})[\"'`]")
CONFIG_RE = re.compile(
    r"[\"']?(apiUrl|baseUrl|base_url|apiBase|serverUrl|endpoint|host|clientId|client_id"
    r"|clientSecret|client_secret|apiKey|api_key|token|accessToken|secret|user|username"
    r"|password|senha|storeId|filial|organizationId|organizationid|domainKey|domainkey)"
    r"[\"']?\s*[:=]\s*[\"']([^\"']{1,120})[\"']",
    re.IGNORECASE,
)

NOISE_HOSTS = (
    "w3.org", "schemas.android.com", "googleapis.com/auth", "gstatic.com",
    "goo.gl", "google.com", "googleadservices.com", "googlesyndication.com",
    "example.com", "capacitorjs.com", "github.com", "npmjs.com", "angular.io",
)


def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="diretório de assets (ou arquivo) a varrer")
    parser.add_argument("--filter", default="", help="mostra apenas hosts/paths contendo este texto")
    parser.add_argument("--show-routes", action="store_true", help="lista também as rotas candidatas")
    parser.add_argument("--show-config", action="store_true", help="lista chaves de configuração")
    parser.add_argument("--json", help="grava o resultado completo neste arquivo")
    args = parser.parse_args()

    root = Path(args.root)
    hosts: dict[str, set[str]] = defaultdict(set)
    hosts_files: dict[str, set[str]] = defaultdict(set)
    routes: dict[str, set[str]] = defaultdict(set)
    config: dict[str, set[str]] = defaultdict(set)

    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        relative = str(path.relative_to(root)) if root.is_dir() else path.name
        for match in URL_RE.finditer(text):
            url = match.group(0).rstrip(".,;)")
            host_match = re.match(r"https?://([^/]+)(/.*)?$", url)
            if not host_match:
                continue
            host, rest = host_match.group(1), host_match.group(2) or ""
            if any(noise in host for noise in NOISE_HOSTS):
                continue
            hosts[host].add(rest[:120])
            hosts_files[host].add(relative)
        for match in ROUTE_RE.finditer(text):
            route = match.group(1)
            if route.startswith("//") or route.count("/") < 2:
                continue
            if any(token in route for token in (".js", ".css", ".png", ".svg", ".jpg", ".woff")):
                continue
            if re.match(r"^/(api|v\d|rest|graphql|mobile|services?|painel|loja|tenant|filial)", route):
                routes[route].add(relative)
        for match in CONFIG_RE.finditer(text):
            key, value = match.group(1), match.group(2)
            if len(value) > 1:
                config[key.lower()].add(f"{value}  [{relative}]")

    needle = args.filter.lower()

    print(f"=== hosts ({len(hosts)}) ===")
    for host in sorted(hosts):
        if needle and needle not in host.lower() and not any(needle in p.lower() for p in hosts[host]):
            continue
        paths = sorted(hosts[host])[:6]
        print(f"\n  {host}   ({len(hosts_files[host])} arquivo(s))")
        for path in paths:
            print(f"      {path}")

    if args.show_routes:
        print(f"\n=== rotas candidatas ({len(routes)}) ===")
        for route in sorted(routes):
            if needle and needle not in route.lower():
                continue
            print(f"  {route}")
            for source in sorted(routes[route])[:2]:
                print(f"      em {source}")

    if args.show_config:
        print(f"\n=== chaves de configuração ({len(config)}) ===")
        for key in sorted(config):
            values = sorted(config[key])[:8]
            print(f"\n  {key}:")
            for value in values:
                print(f"      {value}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "hosts": {host: sorted(paths) for host, paths in hosts.items()},
                    "routes": {route: sorted(files) for route, files in routes.items()},
                    "config": {key: sorted(values) for key, values in config.items()},
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"\nresultado completo -> {args.json}")


if __name__ == "__main__":
    main()
