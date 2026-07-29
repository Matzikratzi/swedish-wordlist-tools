from __future__ import annotations

import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://spraakbanken.gu.se/resurser/data/karp/saol14-faksimil.jsonl"
DEFAULT_OUTPUT = Path("data/raw/saol14-faksimil.jsonl")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, output: Path, overwrite: bool = False) -> Path:
    if output.exists() and not overwrite:
        raise FileExistsError(f"{output} already exists; use --force to replace it")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".part")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "swedish-wordlist-tools/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with temporary.open("wb") as target:
                shutil.copyfileobj(response, target)
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download SAOL 14 JSONL")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    path = download(args.url, args.output, overwrite=args.force)
    print(f"Downloaded: {path}")
    print(f"Bytes:      {path.stat().st_size}")
    print(f"SHA-256:    {sha256_file(path)}")


if __name__ == "__main__":
    main()
