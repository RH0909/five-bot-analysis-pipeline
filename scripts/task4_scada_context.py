"""
Task 4 — SCADA Context Extraction
Vesi Oy Pump Station 3

For each WAV session date, extracts SCADA rows within ±6 hours,
computes mean and std for key channels, writes scada_context.json.
"""
import json, sys
from pathlib import Path
from datetime import datetime, timedelta

ROOT    = Path("/home/roy/work/projects/Client")
SCADA   = ROOT / "data" / "automation" / "scada_data.csv"
OUTPUT  = ROOT / "scada_context.json"
WINDOW  = timedelta(hours=6)

WAV_DATES = [
    "2024-09-15",
    "2024-10-17",
    "2024-11-14",
    "2024-12-12",
]
# Recording time assumed noon if not in filename
RECORDING_HOUR = 12

COLS = ["rpm", "flow_rate_m3h",
        "temp_bearing_drive_end_c", "temp_bearing_non_drive_end_c",
        "vibration_overall_mms", "power_kw"]

# --- Load SCADA ---
if not SCADA.exists():
    print(f"ERROR: scada_data.csv not found at {SCADA}")
    sys.exit(1)

import csv
rows_all = []
with open(SCADA, newline="") as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames
    print(f"SCADA columns: {headers}")
    for row in reader:
        rows_all.append(row)

print(f"SCADA rows loaded: {len(rows_all)}")

# Parse timestamps
ts_col = next((c for c in (headers or [])
               if "time" in c.lower() or "stamp" in c.lower()), None)
if not ts_col:
    print(f"ERROR: no timestamp column found in {headers}")
    sys.exit(1)
print(f"Timestamp column: '{ts_col}'\n")

def parse_ts(val):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(val.strip(), fmt)
        except ValueError:
            continue
    return None

def mean_std(values):
    if not values:
        return None, None
    n   = len(values)
    avg = sum(values) / n
    std = (sum((x - avg) ** 2 for x in values) / n) ** 0.5
    return round(avg, 4), round(std, 4)

# --- Extract window for each session ---
results = []
for date_str in WAV_DATES:
    centre = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=RECORDING_HOUR)
    t_start = centre - WINDOW
    t_end   = centre + WINDOW

    window_rows = []
    for row in rows_all:
        ts = parse_ts(row.get(ts_col, ""))
        if ts and t_start <= ts <= t_end:
            window_rows.append(row)

    if not window_rows:
        print(f"DISCREPANCY: {date_str} — 0 SCADA rows in ±6h window "
              f"({t_start} – {t_end})")

    entry = {
        "session_date":  date_str,
        "window_start":  t_start.isoformat(),
        "window_end":    t_end.isoformat(),
        "row_count":     len(window_rows),
    }

    for col in COLS:
        if col not in (headers or []):
            print(f"DISCREPANCY: column '{col}' not in SCADA headers")
            continue
        vals = []
        for row in window_rows:
            try:
                vals.append(float(row[col]))
            except (ValueError, TypeError):
                pass
        avg, std = mean_std(vals)
        entry[f"{col}_mean"] = avg
        entry[f"{col}_std"]  = std

    results.append(entry)
    print(f"{'OK' if window_rows else 'DISCREPANCY'}: {date_str} — "
          f"{len(window_rows)} rows  "
          f"bearing_temp_mean={entry.get('temp_bearing_drive_end_c_mean')}")

# --- Write output ---
OUTPUT.write_text(json.dumps(results, indent=2))
print(f"\nOutput: {OUTPUT}")
print("COMPLETE: Task 4 — SCADA context extraction done")
