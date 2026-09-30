#!/usr/bin/env python3
"""Report unexpected workspace entries without moving or deleting anything."""
import argparse
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    allowed = set(json.loads(Path(__file__).with_name("top_level_allowlist.json").read_text()))
    entries = sorted(entry.name for entry in args.root.iterdir())
    unexpected = [name for name in entries if name not in allowed]
    result = {"root": str(args.root), "top_count": len(entries), "unexpected": unexpected}
    print(json.dumps(result, ensure_ascii=False) if args.json else "Top-level entries: %s\nUnexpected: %s" % (len(entries), ", ".join(unexpected) or "none"))
    return 1 if unexpected else 0

if __name__ == "__main__":
    raise SystemExit(main())
