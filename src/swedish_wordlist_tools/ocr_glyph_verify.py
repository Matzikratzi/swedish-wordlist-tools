from __future__ import annotations

import csv
import subprocess
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

from .ocr_saol_normalize import normalize_text_for_match


@dataclass(frozen=True)
class GlyphVerification:
    expected: str
    observed_ocr: str
    bbox: tuple[int, int, int, int]
    lexical_similarity: float
    expected_pixel_score: float
    ocr_pixel_score: float
    pixel_advantage: float
    verified: bool
    font: str
    size: int


def _compact(text: str) -> str:
    return "".join(ch for ch in normalize_text_for_match(text) if ch.isalnum() or ch == "-")


def _fonts() -> list[str]:
    patterns = ("serif:style=Bold", "Times New Roman:style=Bold", "Liberation Serif:style=Bold")
    found: list[str] = []
    for pattern in patterns:
        try:
            out = subprocess.check_output(["fc-match", "-f", "%{file}\n", pattern], text=True)
        except (OSError, subprocess.CalledProcessError):
            continue
        for line in out.splitlines():
            path = line.strip()
            if path and path not in found:
                found.append(path)
    return found


def _trim(img: Image.Image) -> Image.Image:
    gray = img.convert("L")
    inv = ImageChops.invert(gray)
    bbox = inv.getbbox()
    return gray.crop(bbox) if bbox else gray


def _render(text: str, font_path: str, size: int) -> Image.Image:
    font = ImageFont.truetype(font_path, size=size)
    bbox = font.getbbox(text)
    w = max(1, bbox[2] - bbox[0] + 8)
    h = max(1, bbox[3] - bbox[1] + 8)
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    draw.text((4 - bbox[0], 4 - bbox[1]), text, fill=0, font=font)
    return _trim(img)


def _score(observed: Image.Image, rendered: Image.Image) -> float:
    obs = _trim(observed)
    if not obs.width or not obs.height or not rendered.width or not rendered.height:
        return 1.0
    test = rendered.resize(obs.size, Image.Resampling.LANCZOS)
    diff = ImageChops.difference(obs, test)
    vals = list(diff.getdata())
    return sum(vals) / (255.0 * len(vals)) if vals else 1.0


def _best_word(tsv: Path, expected: str) -> tuple[str, tuple[int, int, int, int], float] | None:
    target = _compact(expected)
    if not target:
        return None
    best = None
    with tsv.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row.get("level") != "5" or not row.get("text"):
                continue
            observed = row["text"]
            obs_compact = _compact(observed)
            if not obs_compact:
                continue
            ratio = SequenceMatcher(None, target, obs_compact).ratio()
            # Avoid unrelated short words winning just because of a few letters.
            if abs(len(target) - len(obs_compact)) > max(3, len(target) // 3):
                continue
            candidate = (
                observed,
                (int(row["left"]), int(row["top"]), int(row["width"]), int(row["height"])),
                ratio,
            )
            if best is None or ratio > best[2]:
                best = candidate
    return best


def verify_expected_headword(image: Path, tsv: Path, expected: str) -> GlyphVerification | None:
    match = _best_word(tsv, expected)
    if match is None:
        return None
    observed_ocr, bbox, lexical_similarity = match
    x, y, w, h = bbox
    observed = Image.open(image).convert("L").crop((x, y, x + w, y + h))

    best_expected = (1.0, "", 0)
    best_ocr = (1.0, "", 0)
    for font_path in _fonts():
        for size in range(8, 23):
            expected_score = _score(observed, _render(expected, font_path, size))
            if expected_score < best_expected[0]:
                best_expected = (expected_score, font_path, size)
            ocr_score = _score(observed, _render(observed_ocr, font_path, size))
            if ocr_score < best_ocr[0]:
                best_ocr = (ocr_score, font_path, size)

    advantage = best_ocr[0] - best_expected[0]
    # Whole-word template verification is only a tie-breaker. Require both a
    # strong lexical near-match and a visible pixel advantage for the JSONL form.
    verified = lexical_similarity >= 0.72 and advantage >= 0.015
    return GlyphVerification(
        expected=expected,
        observed_ocr=observed_ocr,
        bbox=bbox,
        lexical_similarity=round(lexical_similarity, 4),
        expected_pixel_score=round(best_expected[0], 6),
        ocr_pixel_score=round(best_ocr[0], 6),
        pixel_advantage=round(advantage, 6),
        verified=verified,
        font=best_expected[1],
        size=best_expected[2],
    )


def verification_dict(result: GlyphVerification | None) -> dict[str, object] | None:
    return asdict(result) if result is not None else None
