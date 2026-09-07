from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write a new manual pixel atlas with one label removed from all annotations."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    words = data.get("words")
    if not isinstance(words, list):
        raise SystemExit("input atlas has no words list")

    removed = 0
    affected_words = 0
    examples: list[dict[str, object]] = []

    for word in words:
        if not isinstance(word, dict):
            continue
        anns = word.get("annotations")
        if not isinstance(anns, list):
            continue
        kept = []
        word_removed = 0
        for ann in anns:
            if isinstance(ann, dict) and ann.get("label") == args.label:
                removed += 1
                word_removed += 1
                if len(examples) < 20:
                    examples.append({
                        "page": word.get("page"),
                        "subnr": word.get("subnr"),
                        "headword": word.get("headword") or word.get("expected_word"),
                        "style": word.get("style"),
                        "candidate_status": ann.get("candidate_status"),
                    })
                continue
            kept.append(ann)
        if word_removed:
            affected_words += 1
            word["annotations"] = kept

    history = data.setdefault("migration_history", [])
    if isinstance(history, list):
        history.append({
            "operation": "drop_label",
            "label": args.label,
            "removed_annotations": removed,
            "affected_words": affected_words,
            "reason": "label semantics reset; old annotations are intentionally not reinterpreted",
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"label={args.label!r}")
    print(f"removed_annotations={removed}")
    print(f"affected_words={affected_words}")
    print(f"output={args.output}")
    if examples:
        print("examples:")
        for item in examples:
            print(
                f"  page={item['page']} subnr={item['subnr']} style={item['style']} "
                f"word={item['headword']!r} status={item['candidate_status']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
