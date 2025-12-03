#!/usr/bin/env python3
"""
pull.py - DataTable scraper that outputs JSON by default and optionally a pretty table.

Default behavior:
  - Connects to remote Selenium (--selenium or env SELENIUM_URL)
  - Loads URL built from --mech and --url-template (replace {variable})
  - Waits for DataTable rows and parses header + rows
  - Filters by --variant if provided (case-insensitive substring match)
  - By default prints JSON array to stdout: [{header1: val, header2: val, ...}, ...]
  - If --table is present, prints a human-friendly table instead (uses rich if installed)
  - If --out is provided, writes units.csv and units.json into that directory

Exit codes:
  0 success (and prints JSON/table)
  1 no rows parsed / page problem
  2 selenium connection error or variant not found
"""

import os
import sys
import time
import argparse
import csv
import json
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
from bs4 import BeautifulSoup

# Optional pretty printing with rich
try:
    from rich.console import Console
    from rich.table import Table as RichTable
    RICH_AVAILABLE = True
    console = Console()
except Exception:
    RICH_AVAILABLE = False
    console = None

# Defaults
DEFAULT_SELENIUM = os.environ.get("SELENIUM_URL", "http://192.168.1.9:4444/wd/hub")
DEFAULT_TIMEOUT = 25
TABLE_SELECTOR = "table#DataTables_Table_0"

def build_remote_driver(remote_url: str):
    chrome_opts = Options()
    chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--window-size=1920,1080")
    # allow site to load despite hostname cert issues seen previously
    chrome_opts.add_argument("--ignore-certificate-errors")
    chrome_opts.add_argument("--allow-insecure-localhost")

    try:
        driver = webdriver.Remote(command_executor=remote_url, options=chrome_opts, keep_alive=True)
    except WebDriverException as e:
        raise RuntimeError(f"Could not create remote WebDriver at {remote_url}: {e}")
    driver.implicitly_wait(2)
    return driver

def parse_table(html: str):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(TABLE_SELECTOR)
    if not table:
        return None, []

    # headers
    headers = []
    thead = table.find("thead")
    if thead:
        ths = thead.find_all("th")
        headers = [th.get_text(strip=True) or "" for th in ths]

    # rows
    rows = []
    for tr in table.select("tbody tr"):
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        rows.append(cols)

    return headers, rows

def normalize_rows_with_headers(headers, rows):
    """Return headers (filled) and list of dicts mapping header->value."""
    if not headers:
        # generate headers from the widest row
        maxc = max((len(r) for r in rows), default=0)
        headers = [f"col{i}" for i in range(maxc)]
    max_cols = max(len(headers), max((len(r) for r in rows), default=0))
    norm_headers = headers + [f"col{i}" for i in range(len(headers), max_cols)]
    dict_rows = []
    for r in rows:
        padded = r + [""] * (max_cols - len(r))
        d = {norm_headers[i]: padded[i] for i in range(max_cols)}
        dict_rows.append(d)
    return norm_headers, dict_rows

def filter_by_variant(dict_rows, variant):
    if not variant:
        return dict_rows
    v = variant.lower()
    matched = []
    for d in dict_rows:
        # if any value contains the substring (case-insensitive)
        for val in d.values():
            if v in (val or "").lower():
                matched.append(d)
                break
    return matched

def print_table(headers, dict_rows, variant=None):
    """Pretty-print table to terminal (rich if available)."""
    variant_lower = variant.lower() if variant else None
    if RICH_AVAILABLE:
        t = RichTable(show_lines=False)
        for h in headers:
            t.add_column(h or "")
        for d in dict_rows:
            cells = []
            for h in headers:
                text = d.get(h, "") or ""
                if variant_lower and variant_lower in text.lower():
                    text = f"[bold yellow]{text}[/]"
                cells.append(text)
            t.add_row(*cells)
        console.print(t)
    else:
        # fallback pipe-separated
        print(" | ".join(headers))
        print("-" * min(200, max(20, len(" | ".join(headers)))))
        for d in dict_rows:
            cells = []
            for h in headers:
                text = d.get(h, "") or ""
                if variant_lower and variant_lower in text.lower():
                    text = f">>{text}<<"
                cells.append(text)
            print(" | ".join(cells))
    print(f"\nTotal rows: {len(dict_rows)}", file=sys.stderr)

def save_outputs(headers, dict_rows, outdir):
    if not outdir:
        return
    try:
        os.makedirs(outdir, exist_ok=True)
    except Exception as e:
        print(f"[!] Could not create output directory {outdir}: {e}", file=sys.stderr)
        return

    csv_path = os.path.join(outdir, "units.csv")
    json_path = os.path.join(outdir, "units.json")

    # write CSV
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for d in dict_rows:
                writer.writerow([d.get(h, "") for h in headers])
        print(f"[+] Wrote CSV -> {csv_path}", file=sys.stderr)
    except Exception as e:
        print(f"[!] Failed to write CSV: {e}", file=sys.stderr)

    # write JSON (array of objects)
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(dict_rows, f, ensure_ascii=False, indent=2)
        print(f"[+] Wrote JSON -> {json_path}", file=sys.stderr)
    except Exception as e:
        print(f"[!] Failed to write JSON: {e}", file=sys.stderr)

def run(args):
    mech = args.mech.strip()
    if not mech:
        print("[!] --mech is required", file=sys.stderr)
        return 1

    encoded = quote_plus(mech)
    template = args.url_template
    if "{variable}" not in template:
        url = template + encoded
    else:
        url = template.replace("{variable}", encoded)

    # Optional MUL type filter (e.g., 19 for vehicles, 18 for aerospace, 4 for BA, 10 for infantry)
    if args.types:
        url = f"{url}&Types={quote_plus(str(args.types))}"

    selenium_url = args.selenium
    try:
        driver = build_remote_driver(selenium_url)
    except Exception as e:
        print(f"[!] Selenium connection error: {e}", file=sys.stderr)
        return 2

    try:
        driver.get(url)
        wait = WebDriverWait(driver, args.timeout)
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, f"{TABLE_SELECTOR} tbody tr")))
            time.sleep(0.5)
        except TimeoutException:
            print("[!] Timeout waiting for table rows; parsing whatever is present", file=sys.stderr)

        html = driver.page_source
        headers, rows = parse_table(html)
        if not rows:
            print("[!] No rows parsed from page.", file=sys.stderr)
            print(html[:2000].replace("\n", " "), file=sys.stderr)
            return 1

        headers_filled, dict_rows = normalize_rows_with_headers(headers, rows)

        # filter by variant if provided
        dict_rows_filtered = filter_by_variant(dict_rows, args.variant)
        if args.variant and not dict_rows_filtered:
            print(f"[!] No rows matched variant '{args.variant}'", file=sys.stderr)
            # still save full data if requested
            if args.out:
                save_outputs(headers_filled, dict_rows, args.out)
            return 2

        # if out requested, save filtered (or full) rows as files
        if args.out:
            save_outputs(headers_filled, dict_rows_filtered if args.variant else dict_rows, args.out)

        # Output:
        if args.table:
            print_table(headers_filled, dict_rows_filtered if args.variant else dict_rows, variant=args.variant)
            return 0
        else:
            # Default: print JSON array to stdout (dict_rows_filtered contains dicts)
            # Ensure deterministic header order by using headers_filled for each object
            output_list = []
            for d in (dict_rows_filtered if args.variant else dict_rows):
                # make ordered dict-like mapping using headers_filled order
                ordered = {h: d.get(h, "") for h in headers_filled}
                output_list.append(ordered)
            json.dump(output_list, sys.stdout, ensure_ascii=False)
            sys.stdout.write("\n")
            return 0

    finally:
        try:
            driver.quit()
        except Exception:
            pass

def main():
    parser = argparse.ArgumentParser(description="Scrape masterunitlist.info DataTable and output JSON (default) or table (--table).")
    parser.add_argument("--mech", required=True, help="Mech name to search (e.g. 'Archer')")
    parser.add_argument("--variant", default=None, help="Optional variant substring to filter rows (case-insensitive)")
    parser.add_argument("--selenium", default=DEFAULT_SELENIUM, help=f"Remote Selenium URL (default: env SELENIUM_URL or {DEFAULT_SELENIUM})")
    parser.add_argument("--out", default=None, help="Optional output directory to save units.csv and units.json")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Seconds to wait for table render")
    parser.add_argument("--url-template", default="https://masterunitlist.info/Unit/Filter?Name={variable}&HasBV=true&HasBV=false&MinTons=&MaxTons=&MinBV=&MaxBV=&MinIntro=&MaxIntro=&MinCost=&MaxCost=&HasBFAbility=&MinPV=&MaxPV=&BookAuto=&FactionAuto=", help="URL template with {variable} placeholder")
    parser.add_argument("--types", default=None, help="Optional MUL Types filter (e.g., 19=vehicles, 18=aero, 4=BA, 10=infantry)")
    parser.add_argument("--table", action="store_true", help="Print a human-readable table instead of JSON")
    args = parser.parse_args()

    try:
        rc = run(args)
        sys.exit(rc)
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)

if __name__ == "__main__":
    main()
