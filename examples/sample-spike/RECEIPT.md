# Receipt: Turn a text table into JSON

Every section below must be filled in before this spike can be closed.

## What now exists

table_to_json.py reads a text file with one name and one whole number per line and prints a JSON list of objects with the keys name and count. sample.txt is a three-row input. verify.sh is the check.

## How to run it

Run `python3 table_to_json.py sample.txt` in this folder. It prints `[{"name": "alder", "count": 12}, {"name": "birch", "count": 7}, {"name": "cedar", "count": 31}]`. Run `sh verify.sh` to run the check; it exits 0 when the output parses and holds the three names.

## What it proved

A plain text table can be turned into JSON with the standard library alone, in about thirty lines, and the output can be checked by a script that needs no other tools.

## What it did not do

It does not handle names with spaces, quoted fields, negative numbers, decimals or tab-separated files. A malformed line stops it with an error. It was tried on one three-row file only.

## Next step

Decide whether the tables you actually have fit this shape. If they do, add the handling for spaces and decimals. If they do not, stop here.
