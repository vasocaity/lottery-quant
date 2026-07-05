#!/usr/bin/env python3
"""
Re-import lottery draw data from an HTML file into the backend.

Usage:
    python3 scripts/reimport.py path/to/results.html
    python3 scripts/reimport.py path/to/results.html --url http://localhost:3001
    python3 scripts/reimport.py path/to/results.html --dry-run
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Allow importing lottery_extract from ml-service/app without installing it
sys.path.insert(0, str(Path(__file__).parent.parent / "ml-service"))
from app.lottery_extract import extract_draws

DEFAULT_BACKEND = "http://localhost:3001/api"


def post_json(url: str, body: dict | None = None) -> dict:
    payload = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else b""
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser(description="Extract + import lottery draws into the backend")
    parser.add_argument("html", help="Path to the lottery results HTML file")
    parser.add_argument("--url", default=DEFAULT_BACKEND, help=f"Backend base URL (default: {DEFAULT_BACKEND})")
    parser.add_argument("--dry-run", action="store_true", help="Extract only — don't POST to backend")
    parser.add_argument("--skip-retrain", action="store_true", help="Import draws but skip retrain + predict step")
    args = parser.parse_args()

    html_path = Path(args.html)
    if not html_path.exists():
        print(f"Error: file not found → {html_path}", file=sys.stderr)
        sys.exit(1)

    html = html_path.read_text(encoding="utf-8")
    draws = extract_draws(html)

    if not draws:
        print("Warning: no draws extracted — check that the HTML structure matches.", file=sys.stderr)
        sys.exit(1)

    print(f"Extracted {len(draws)} draws from {html_path.name}")

    if args.dry_run:
        print(json.dumps({"draws": draws}, ensure_ascii=False, indent=2))
        return

    base = args.url.rstrip("/")
    chunk_size = 300
    chunks = [draws[i:i + chunk_size] for i in range(0, len(draws), chunk_size)]
    total_imported = 0

    for idx, chunk in enumerate(chunks, start=1):
        print(f"Sending chunk {idx}/{len(chunks)} ({len(chunk)} rows)…")
        try:
            result = post_json(f"{base}/draws/import", {"items": chunk})
            total_imported += result.get("imported", 0)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"HTTP {e.code} on chunk {idx}: {body}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(f"Could not reach backend at {base}: {e.reason}", file=sys.stderr)
            print("Is the backend running? Start with: docker compose up backend", file=sys.stderr)
            sys.exit(1)

    print(f"Imported {total_imported} draws total.")

    if args.skip_retrain:
        print("Skipping retrain (--skip-retrain set).")
        return

    print("Retraining model on updated draws…")
    try:
        post_json(f"{base}/predictions/train")
        print("Training done. Running predictions…")
        post_json(f"{base}/predictions/run")
        print("Done — model retrained and new predictions generated.")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"HTTP {e.code} during retrain/predict: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Could not reach backend during retrain: {e.reason}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
