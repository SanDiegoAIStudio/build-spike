#!/bin/sh
# Exits 0 only when the converter prints a JSON list holding the three names.
cd "$(dirname "$0")" || exit 1
python3 table_to_json.py sample.txt | python3 -c '
import json, sys
rows = json.load(sys.stdin)
names = sorted(row["name"] for row in rows)
sys.exit(0 if names == ["alder", "birch", "cedar"] else 1)
'
