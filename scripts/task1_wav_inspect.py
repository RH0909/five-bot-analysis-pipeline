"""
Task 1 — WAV File Inspection
Vesi Oy Pump Station 3

Reads header of all four WAV files, compares against measurement_setup.json,
flags discrepancies, writes wav_inspection.json.
"""
import json, sys
from pathlib import Path
import soundfile as sf

ROOT = Path(os.environ.get("FBA_ROOT") or Path(__file__).resolve().parent.parent)
BG       = ROOT / "background"
ACOUSTIC = ROOT / "data" / "acoustic"
OUTPUT   = ROOT / "wav_inspection.json"
WAV_FILES = [ACOUSTIC / f"acoustic_{d}.wav" for d in [
    "2024-09-15", "2024-10-17", "2024-11-14", "2024-12-12"
]]

# --- Load spec ---
spec_path = next((p for p in [BG / "measurement_setup.json",
                               ROOT / "measurement_setup.json"] if p.exists()), None)
if not spec_path:
    print("ERROR: measurement_setup.json not found in Client/ or Client/background/")
    sys.exit(1)

spec = json.loads(spec_path.read_text())
print(f"Spec loaded: {spec_path}")
print(f"Spec keys: {list(spec.keys())}")

# Nested spec — dig into sub-sections for expected values
daq = spec.get("data_acquisition") or {}
acc = spec.get("accelerometers")
if isinstance(acc, list) and acc:
    acc = acc[0]
elif not isinstance(acc, dict):
    acc = {}

print(f"data_acquisition keys: {list(daq.keys())}")
print(f"accelerometers keys:   {list(acc.keys())}\n")

def _find(dicts, keys):
    for d in dicts:
        for k in keys:
            if k in d:
                return d[k]
    return None

exp_sr = _find([daq, spec], ["sample_rate_hz", "sample_rate", "samplerate",
               "sampling_rate", "fs", "rate"])
exp_ch = _find([spec, daq], ["channels", "channel_count", "num_channels",
               "n_channels", "total_channels"])
# Fallback: count the accelerometers list (1 entry → 1 channel recorded)
if exp_ch is None:
    accs = spec.get("accelerometers")
    if isinstance(accs, list):
        exp_ch = len(accs)
exp_bd = _find([daq, acc, spec], ["resolution_bits", "bit_depth", "bits_per_sample",
               "resolution", "bits"])
ch_map = spec.get("channel_map") or spec.get("channels_map") or {}

print(f"Expected — rate: {exp_sr} Hz  channels: {exp_ch}  bit_depth: {exp_bd}")
print(f"Channel map: {ch_map}\n")

# --- Inspect each WAV ---
results = []
for path in WAV_FILES:
    if not path.exists():
        print(f"ERROR: {path.name} not found at {path}")
        results.append({"filename": path.name, "error": "file not found"})
        continue

    info = sf.info(str(path))
    disc = []
    if exp_sr and info.samplerate != int(exp_sr):
        disc.append(f"sample_rate: got {info.samplerate}, expected {exp_sr}")
    if exp_ch and info.channels != int(exp_ch):
        disc.append(f"channels: got {info.channels}, expected {exp_ch}")
    # Parse bit depth from subtype string (e.g. "PCM_16" → 16, "PCM_24" → 24)
    if exp_bd:
        parts = info.subtype.split("_")
        wav_bd = int(parts[-1]) if parts[-1].isdigit() else None
        if wav_bd is not None and wav_bd != int(exp_bd):
            disc.append(f"bit_depth: got {wav_bd} (subtype={info.subtype}), "
                        f"expected {exp_bd}")

    entry = {
        "filename":        path.name,
        "sample_rate_hz":  info.samplerate,
        "subtype":         info.subtype,
        "channels":        info.channels,
        "duration_s":      round(info.duration, 2),
        "channel_0_label": ch_map.get("0") or ch_map.get(0) or "ACC-DE (assumed)",
        "discrepancies":   disc,
    }
    results.append(entry)

    for d in disc:
        print(f"DISCREPANCY: {path.name} — {d}")
    if not disc:
        print(f"OK: {path.name} — {info.samplerate} Hz  {info.channels} ch  "
              f"{info.subtype}  {info.duration:.1f}s")

# --- Write output ---
OUTPUT.write_text(json.dumps(results, indent=2))
print(f"\nOutput: {OUTPUT}")
print("COMPLETE: Task 1 — WAV inspection done")
