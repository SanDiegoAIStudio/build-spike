#!/bin/sh
python3 main.py > out.txt
grep -q ok out.txt
