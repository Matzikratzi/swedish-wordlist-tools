from __future__ import annotations

import argparse
import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE = "https://spraakbanken4.it.gu.se/karps/v1/"
DEFAULT_OUT = Path("reports/karp-saol14-probe.json")
DEFAULT_WORDS = ("halländska", "hajp", "akne", "ankare")


def build_ssl_context(*, insecure: bool = False) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    try:
        import certifi  # type: ignore
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def fetch_json(url: str, *, context: ssl.SSLContext) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "swedish-wordlist-tools/karp-probe"})
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        return json.load(response)


def resource_entry_word_field(config: dict[str, Any], resource: str) -> str:
    for item in config.get("resources", []):
        if item.get("resourceId") == resource:
            entry_word = item.get("entryWord") or {}
            field = entry_word.get("field")
            if field:
                return str(field)
            raise ValueError(f"Resource {resource!r} has no entryWord field in Karp config")
    raise ValueError(f"Resource {resource!r} not found in Karp config")


def build_search_url(base: str, resource: str, field: str, word: str, size: int = 20) -> str:
    q = f'{field} = "{word}"'
    params = urllib.parse.urlencode({"resources": resource, "q": q, "size": size})
    return f"{base.rstrip('/')}/search?{params}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Karp SAOL14 schema and raw entries")
    parser.add_argument("--base", default=DEFAULT_BASE, help="Karp-s API base URL")
    parser.add_argument("--resource", default="saol14-faksimil", help="Karp resource id")
    parser.add_argument("--word", action="append", dest="words", help="Word to query; repeatable")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification for this diagnostic probe only",
    )
    args = parser.parse_args()

    words = tuple(args.words or DEFAULT_WORDS)
    context = build_ssl_context(insecure=args.insecure)
    result: dict[str, Any] = {
        "base": args.base,
        "resource": args.resource,
        "words": words,
        "insecure": args.insecure,
    }

    config_url = f"{args.base.rstrip('/')}/config"
    result["config_url"] = config_url
    try:
        config = fetch_json(config_url, context=context)
        result["config"] = config
        entry_word_field = resource_entry_word_field(config, args.resource)
        result["entry_word_field"] = entry_word_field
    except Exception as exc:
        result["config_error"] = f"{type(exc).__name__}: {exc}"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Karp config failed: {type(exc).__name__}: {exc}")
        print(f"Output: {args.out}")
        if not args.insecure:
            print("Retry diagnostically with: python -m swedish_wordlist_tools.probe_karp_saol14 --insecure")
        return

    searches: dict[str, Any] = {}
    for word in words:
        url = build_search_url(args.base, args.resource, entry_word_field, word)
        try:
            payload = fetch_json(url, context=context)
            searches[word] = {"url": url, "payload": payload}
        except Exception as exc:
            searches[word] = {"url": url, "error": f"{type(exc).__name__}: {exc}"}
    result["searches"] = searches

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Karp config: {config_url}")
    print(f"Resource: {args.resource}")
    print(f"Entry word field: {entry_word_field}")
    print(f"Words: {', '.join(words)}")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    main()
