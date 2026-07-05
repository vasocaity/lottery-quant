#!/usr/bin/env python3
"""
Thai Government Lottery HTML → JSON Extractor
=============================================
Parses the result-history HTML from thailottery.official-data.com (or similar sites)
and outputs a structured JSON array of draw results.

Usage:
    python3 lottery_extract.py input.html
    python3 lottery_extract.py input.html --output results.json
    python3 lottery_extract.py input.html --pretty
"""

import re
import json
import sys
import argparse
from pathlib import Path


# Thai month name → zero-padded month number
MONTH_MAP = {
    "มกราคม":   "01",
    "กุมภาพันธ์": "02",
    "มีนาคม":   "03",
    "เมษายน":   "04",
    "พฤษภาคม":  "05",
    "มิถุนายน":  "06",
    "กรกฎาคม":  "07",
    "สิงหาคม":  "08",
    "กันยายน":  "09",
    "ตุลาคม":   "10",
    "พฤศจิกายน": "11",
    "ธันวาคม":  "12",
}

BUDDHIST_ERA_OFFSET = 543  # subtract to convert พ.ศ. → ค.ศ. (CE)


def extract_draws(html: str) -> list[dict]:
    """
    Extract lottery draw records from raw HTML.

    Each <div class="rowx"> row contains divs with class "row-hld"
    holding the prize numbers in this order:
        [0] first_prize  – 6-digit first prize
        [1] last2        – last 2 digits [2 ตัวบน]
        [2] back3        – last 3 digits [3 ตัวบน]
        [3] front2       – first 2 digits  [2 ตัวล่าง] (sx-hide on mobile, always present)

    The date is split across three plain colx divs (day / month-th / year-BE).
    """
    draws = []

    # Match each row block
    row_pattern = re.compile(
        r'<div class="rowx[^"]*"[^>]*>.*?</div>\s*</div>',
        re.DOTALL
    )

    # Pull all text from a tag's inner content (strips nested tags)
    text_of = lambda tag: re.sub(r"<[^>]+>", "", tag).strip()

    for row_html in row_pattern.findall(html):
        # ── Date columns (first three colx divs) ──────────────────────────
        col_divs = re.findall(
            r'<div class="colx(?:\s+sx-hide)?"[^>]*>(.*?)</div>',
            row_html,
            re.DOTALL
        )
        if len(col_divs) < 3:
            continue

        day_raw    = text_of(col_divs[0])
        month_raw  = text_of(col_divs[1])   # full Thai month name (sx-hide)
        year_be    = text_of(col_divs[2])    # Buddhist Era year  (sx-hide)

        month_th = month_raw.strip()
        if month_th not in MONTH_MAP:
            continue  # skip header / non-data rows

        try:
            day  = int(day_raw)
            year = int(year_be) - BUDDHIST_ERA_OFFSET
        except ValueError:
            continue

        date_str = f"{year}-{MONTH_MAP[month_th]}-{day:02d}"

        # ── Prize columns (row-hld divs) ───────────────────────────────────
        prize_divs = re.findall(
            r'<div class="colx row-hld(?:\s+sx-hide)?"[^>]*>(.*?)</div>',
            row_html,
            re.DOTALL
        )
        if len(prize_divs) < 4:
            continue

        first_prize = text_of(prize_divs[0])
        last2       = text_of(prize_divs[3])
        back3       = text_of(prize_divs[2])
        front2      = text_of(prize_divs[1])

        draws.append({
            "date":       date_str,
            "firstPrize": first_prize,
            "front2":     front2,
            "back3":      back3,
            "last2":      last2,
        })

    return draws


def main():
    parser = argparse.ArgumentParser(
        description="Extract Thai lottery results from HTML to JSON"
    )
    parser.add_argument("input", help="Path to HTML file")
    parser.add_argument(
        "--output", "-o",
        help="Output JSON file path (default: print to stdout)"
    )
    parser.add_argument(
        "--pretty", "-p",
        action="store_true",
        help="Pretty-print JSON with indentation"
    )
    args = parser.parse_args()

    html_path = Path(args.input)
    if not html_path.exists():
        print(f"Error: file not found → {html_path}", file=sys.stderr)
        sys.exit(1)

    html = html_path.read_text(encoding="utf-8")
    draws = extract_draws(html)

    if not draws:
        print("Warning: no draws found. Check that the HTML structure matches.", file=sys.stderr)

    result = {"draws": draws}
    indent = 2 if args.pretty else None
    json_str = json.dumps(result, ensure_ascii=False, indent=indent)

    if args.output:
        Path(args.output).write_text(json_str, encoding="utf-8")
        print(f"✓ Saved {len(draws)} draws → {args.output}")
    else:
        print(json_str)


if __name__ == "__main__":
    main()