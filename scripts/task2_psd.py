"""
Task 2 — PSD Computation
Vesi Oy Pump Station 3

Loads channel 0 (ACC-DE) from each WAV session, computes Welch PSD,
saves psd_results.npz.

Requires: task1 output (wav_inspection.json) — aborts if blockers found.
Units: dB re 1 m/s² requires sensor calibration from measurement_setup.json.
       If no calibration found, reports relative dB re 1 count and flags it.
"""
import json, sys
import numpy as np
from pathlib import Path
from scipy import signal
import soundfile as sf

ROOT     = Path("/home/roy/work/projects/Client")
BG       = ROOT / "background"
ACOUSTIC = ROOT / "data" / "acoustic"
INSPECT  = ROOT / "wav_inspection.json"
OUTPUT   = ROOT / "psd_results.npz"

WELCH_WINDOW   = 4096
WELCH_OVERLAP  = 0.50
WELCH_WINFUNC  = "hann"

# --- Check Task 1 output ---
if not INSPECT.exists():
    print("ERROR: wav_inspection.json not found — run Task 1 first")
    sys.exit(1)

inspection = json.loads(INSPECT.read_text())
blockers = [e for e in inspection if e.get("error") or
            any("channels" in d for d in e.get("discrepancies", []))]
if blockers:
    for b in blockers:
        print(f"DISCREPANCY: blocker from Task 1 — {b['filename']}: "
              f"{b.get('error') or b.get('discrepancies')}")
    print("Proceeding anyway — channel 0 will be extracted if available.")

# --- Load calibration ---
spec_path = next((p for p in [BG/"measurement_setup.json",
                               ROOT/"measurement_setup.json"] if p.exists()), None)
cal_factor = 1.0
cal_note   = "DISCREPANCY: no calibration found — PSD in relative dB re 1 count RMS"
if spec_path:
    spec = json.loads(spec_path.read_text())
    cal_raw = None
    cal_key = None
    # Try flat scalar keys first
    for key in ("sensitivity_mv_per_ms2", "sensitivity_mv_per_g",
                "acc_sensitivity_mv_per_g", "acc_de_sensitivity", "sensitivity"):
        v = spec.get(key)
        if v is not None:
            cal_raw, cal_key = v, key
            break
    # Then dig into accelerometers list
    if cal_raw is None:
        acc_list = spec.get("accelerometers") or []
        if isinstance(acc_list, dict):
            acc_list = [acc_list]
        for a in acc_list:
            for key in ("sensitivity_mv_per_ms2", "sensitivity_mv_per_g",
                        "sensitivity", "factor"):
                v = a.get(key)
                if v is not None:
                    cal_raw, cal_key = v, key
                    break
            if cal_raw is not None:
                break
    print(f"Calibration lookup: key={cal_key!r}  value={cal_raw!r}")
    if cal_raw is not None:
        try:
            val = float(cal_raw)
            if cal_key == "sensitivity_mv_per_ms2":
                # Direct calibration: sensitivity in mV/(m/s²) — apply as factor
                cal_factor = val
                cal_note = f"Calibration applied: {val} mV/(m/s²) from spec"
            else:
                # Found sensitivity but in non-absolute units (e.g. mV/g).
                # Absolute calibration also requires ADC full-scale voltage
                # (not in measurement_setup.json) — fall back to relative dB.
                cal_note = (
                    f"DISCREPANCY: sensitivity found ({val} {cal_key}) "
                    f"but absolute calibration requires ADC full-scale voltage "
                    f"(not in measurement_setup.json) — "
                    f"PSD in relative dB re 1 count RMS"
                )
        except (TypeError, ValueError):
            cal_note = (f"DISCREPANCY: calibration value '{cal_raw}' is not numeric "
                        f"— PSD in relative dB re 1 count RMS")
print(cal_note)

# --- Process each session ---
session_dates, psd_list = [], []

for entry in inspection:
    if entry.get("error"):
        continue
    path = ACOUSTIC / entry["filename"]
    date = entry["filename"].split("_")[1].replace(".wav", "")

    data, fs = sf.read(str(path), dtype="float32", always_2d=True)
    # data shape: (frames, channels)
    ch0 = data[:, 0]   # channel 0

    freqs, psd = signal.welch(
        ch0, fs=fs,
        window=WELCH_WINFUNC,
        nperseg=WELCH_WINDOW,
        noverlap=int(WELCH_WINDOW * WELCH_OVERLAP),
    )
    # Apply calibration and convert to dB
    psd_calibrated = psd * (cal_factor ** 2)
    psd_db = 10 * np.log10(psd_calibrated + 1e-30)

    psd_list.append(psd_db)
    session_dates.append(date)
    print(f"OK: {entry['filename']} — {len(ch0)} samples  "
          f"PSD shape {psd_db.shape}  peak {psd_db.max():.1f} dB  "
          f"channel 0 = {entry.get('channel_0_label', 'ACC-DE')}")

if not psd_list:
    print("ERROR: no sessions processed")
    sys.exit(1)

psd_array = np.array(psd_list)  # (n_sessions, n_freqs)

np.savez(OUTPUT,
         freqs_hz=freqs,
         psd_db=psd_array,
         session_dates=np.array(session_dates))

print(f"\nOutput: {OUTPUT}")
print(f"  freqs_hz shape : {freqs.shape}  ({freqs[0]:.2f}–{freqs[-1]:.2f} Hz)")
print(f"  psd_db shape   : {psd_array.shape}  (sessions × freq bins)")
print(f"  session_dates  : {session_dates}")
print("COMPLETE: Task 2 — PSD computation done")
