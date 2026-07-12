"""
Task 3 — Fault Frequency Amplitude Extraction
Vesi Oy Pump Station 3

Reads fault frequencies from pump_info.json (never hardcoded),
extracts PSD amplitude at each fundamental + 2× + 3× harmonic per session,
writes fault_amplitudes.csv.

Requires: psd_results.npz from Task 2.
"""
import json, sys, csv
import numpy as np
from pathlib import Path

ROOT = Path(os.environ.get("FBA_ROOT") or Path(__file__).resolve().parent.parent)
BG      = ROOT / "background"
PSD_NPZ = ROOT / "psd_results.npz"
OUTPUT  = ROOT / "fault_amplitudes.csv"

# --- Load PSD results ---
if not PSD_NPZ.exists():
    print("ERROR: psd_results.npz not found — run Task 2 first")
    sys.exit(1)

data          = np.load(str(PSD_NPZ), allow_pickle=True)
freqs         = data["freqs_hz"]
psd_db        = data["psd_db"]
session_dates = list(data["session_dates"])
freq_res      = freqs[1] - freqs[0]
print(f"PSD loaded: {len(session_dates)} sessions  "
      f"{len(freqs)} bins  resolution {freq_res:.3f} Hz\n")

# --- Load fault frequencies from pump_info.json ---
pump_path = next((p for p in [BG/"pump_info.json",
                               ROOT/"pump_info.json"] if p.exists()), None)
if not pump_path:
    print("ERROR: pump_info.json not found in Client/ or Client/background/")
    sys.exit(1)

pump = json.loads(pump_path.read_text())
print(f"pump_info.json keys: {list(pump.keys())}")

# Navigate nested structure: bearings.drive_end holds the bearing fault freqs
de = (pump.get("bearings") or {}).get("drive_end") or {}
impeller = pump.get("impeller") or {}

def _get(d, *keys):
    """Return first matching key from dict d, as float, or None."""
    for k in keys:
        if k in d:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                pass
    return None

fault_map = {
    "BPFO":      _get(de,       "bpfo_hz", "bpfo", "BPFO"),
    "BPFI":      _get(de,       "bpfi_hz", "bpfi", "BPFI"),
    "BSF":       _get(de,       "bsf_hz",  "bsf",  "BSF"),
    "FTF":       _get(de,       "ftf_hz",  "ftf",  "FTF"),
    "SHAFT_1X":  _get(pump,     "shaft_frequency_hz", "shaft_freq_hz", "shaft_1x"),
    "BLADE_PASS":_get(impeller, "blade_pass_frequency_hz", "blade_pass_freq_hz", "bpf_hz"),
}

missing = [k for k, v in fault_map.items() if v is None]
if missing:
    print(f"DISCREPANCY: could not find frequencies for: {missing}")

fault_map = {k: v for k, v in fault_map.items() if v is not None}
print(f"\nFault frequencies found: {fault_map}\n")

# --- Extract amplitudes ---
def nearest_bin_amplitude(freqs, psd_db, target_hz):
    idx = np.argmin(np.abs(freqs - target_hz))
    return float(psd_db[idx])

rows = []
for i, date in enumerate(session_dates):
    for label, base_hz in fault_map.items():
        for harmonic in [1, 2, 3]:
            freq_hz = base_hz * harmonic
            if freq_hz > freqs[-1]:
                continue
            amp_db = nearest_bin_amplitude(freqs, psd_db[i], freq_hz)
            rows.append({
                "session_date":    date,
                "frequency_label": f"{label}_{harmonic}X" if harmonic > 1 else label,
                "frequency_hz":    round(freq_hz, 3),
                "amplitude_db":    round(amp_db, 3),
            })

# --- Write CSV ---
fieldnames = ["session_date", "frequency_label", "frequency_hz", "amplitude_db"]
with open(OUTPUT, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Rows written: {len(rows)}  ({len(session_dates)} sessions × "
      f"{len(fault_map)} frequencies × up to 3 harmonics)")
print(f"Output: {OUTPUT}")
print("COMPLETE: Task 3 — fault frequency amplitudes done")
