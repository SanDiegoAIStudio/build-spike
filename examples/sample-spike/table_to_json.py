"""Read a text table of names and whole numbers and print it as a JSON list."""
import json
import sys


def parse(text):
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2 or not parts[1].isdigit():
            raise ValueError("line %d: expected a name and a whole number" % number)
        rows.append({"name": parts[0], "count": int(parts[1])})
    return rows


def main(argv):
    if len(argv) != 2:
        print("usage: table_to_json.py FILE", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as handle:
        print(json.dumps(parse(handle.read())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
