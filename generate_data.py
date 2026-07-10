#!/usr/bin/env python3
"""
generate_data.py — Simulated industrial pump sensor data generator.

Produces the complete synthetic dataset for the five-bot-analysis-pipeline demo:
  - background/pump_info.json          Asset specification and fault frequencies
  - background/measurement_setup.json  Sensor and DAQ configuration
  - background/site_info.json          Site metadata and maintenance history
  - data/automation/scada_data.csv     10-minute SCADA time series, Sep–Dec 2024
  - data/acoustic/acoustic_<date>.wav  Four vibration recordings (48 kHz, 1-ch, PCM_16)
  - data/acoustic/measurement_log.json Session metadata

All data is fully synthetic. The bearing fault progression (healthy → incipient →
developing → severe) is physically motivated but not derived from real measurements.

Bearing fault frequencies (SKF 6205-2Z, 9 balls, d=7.94mm, D=38.5mm, α=15°):
  Shaft frequency:  1450/60 = 24.167 Hz
  BPFO = (n/2) * (1 - (d/D)*cos(α)) * (RPM/60) ≈ 87.09 Hz
  BPFI = (n/2) * (1 + (d/D)*cos(α)) * (RPM/60) ≈ 130.41 Hz
  BSF  = (D/(2d)) * (1-(d/D)²·cos²(α)) * (RPM/60) ≈ 56.27 Hz
  FTF  = (1/2) * (1 - (d/D)*cos(α)) * (RPM/60) ≈ 9.68 Hz
  BPF  = 6 * shaft = 145.0 Hz  (blade pass, 6 impeller blades)
"""
import json
import csv
import math
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
from scipy.io import wavfile
from scipy import signal

SEED = 42
ROOT = Path(__file__).parent

# Pump / bearing constants
RPM_NOMINAL   = 1450.0
SHAFT_FREQ    = RPM_NOMINAL / 60.0          # 24.167 Hz
N_BALLS       = 9
BALL_DIA_MM   = 7.94
PITCH_DIA_MM  = 38.5
CONTACT_ANGLE = math.radians(15.0)
_d_D  = BALL_DIA_MM / PITCH_DIA_MM         # 0.2062
_cosA = math.cos(CONTACT_ANGLE)             # 0.9659
BPFO = (N_BALLS / 2) * (1 - _d_D * _cosA) * SHAFT_FREQ          # ≈ 87.09 Hz
BPFI = (N_BALLS / 2) * (1 + _d_D * _cosA) * SHAFT_FREQ          # ≈ 130.41 Hz
BSF  = (PITCH_DIA_MM / (2 * BALL_DIA_MM)) * (1 - _d_D**2 * _cosA**2) * SHAFT_FREQ  # ≈ 56.27 Hz
FTF  = 0.5 * (1 - _d_D * _cosA) * SHAFT_FREQ                     # ≈ 9.68 Hz
BPF  = 6 * SHAFT_FREQ                                              # ≈ 145.0 Hz
MOTOR_ELEC = 100.0                                                  # 2× line frequency (50 Hz grid)

SAMPLE_RATE = 48000
DURATION_S  = 60


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    print("=== Industrial Sensor Data Generator ===")
    print(f"Shaft = {SHAFT_FREQ:.3f} Hz | BPFO = {BPFO:.2f} Hz | "
          f"BPFI = {BPFI:.2f} Hz | BPF = {BPF:.2f} Hz")
    generate_background()
    generate_scada()
    generate_acoustic()
    print("\nDone. All files written.")


# ---------------------------------------------------------------------------
# Background information
# ---------------------------------------------------------------------------
def generate_background():
    print("\n[1/3] Generating background information...")
    out_dir = ROOT / "background"
    out_dir.mkdir(exist_ok=True)

    pump_info = {
        "pump_type": "Centrifugal pump",
        "manufacturer": "Grundfos",
        "model": "CM5-6 A-R-I-E-AVBE",
        "serial_number": "GF-2021-CM5-00847",
        "installation_date": "2021-03-15",
        "nominal_rpm": 1450,
        "motor": {
            "type": "4-pole induction motor",
            "power_kw": 1.1,
            "voltage_v": 400,
            "frequency_hz": 50,
            "nominal_rpm": 1450,
            "service_factor": 1.15
        },
        "impeller": {
            "type": "closed",
            "blade_count": 6,
            "diameter_mm": 130,
            "blade_pass_frequency_hz": round(BPF, 2)
        },
        "bearings": {
            "drive_end": {
                "manufacturer": "SKF",
                "model": "6205-2Z",
                "type": "deep groove ball bearing",
                "ball_count": N_BALLS,
                "ball_diameter_mm": BALL_DIA_MM,
                "pitch_diameter_mm": PITCH_DIA_MM,
                "contact_angle_deg": 15,
                "bpfo_hz": round(BPFO, 2),
                "bpfi_hz": round(BPFI, 2),
                "bsf_hz": round(BSF, 2),
                "ftf_hz": round(FTF, 2)
            },
            "non_drive_end": {
                "manufacturer": "SKF",
                "model": "6204-2Z",
                "type": "deep groove ball bearing",
                "notes": "Smaller bearing, not primary monitoring target"
            }
        },
        "shaft_frequency_hz": round(SHAFT_FREQ, 3),
        "fluid": "Water",
        "design_flow_m3h": 8.5,
        "design_head_m": 42.0,
        "design_efficiency_pct": 68
    }
    _write_json(out_dir / "pump_info.json", pump_info)
    print("  Wrote background/pump_info.json")

    measurement_setup = {
        "accelerometers": [
            {
                "id": "ACC-DE",
                "type": "PCB 603C01",
                "sensitivity_mv_per_g": 100,
                "frequency_range_hz": [0.5, 10000],
                "location": "Drive-end bearing housing",
                "mounting": "Magnetic base, radial direction",
                "distance_from_source_m": 0.05
            }
        ],
        "microphones": [
            {
                "id": "MIC-FF",
                "type": "PCB 130E20 free-field condenser",
                "sensitivity_mv_per_pa": 45,
                "frequency_range_hz": [20, 20000],
                "location": "Free-field, 0.5 m from pump casing, height 0.9 m",
                "mounting": "Tripod, IEC 61672 class 1",
                "distance_from_source_m": 0.5
            },
            {
                "id": "MIC-BH",
                "type": "PCB 378C10",
                "sensitivity_mv_per_pa": 50,
                "frequency_range_hz": [20, 20000],
                "location": "Near drive-end bearing housing, 0.1 m from casing",
                "mounting": "Surface mount adapter",
                "distance_from_source_m": 0.1
            }
        ],
        "data_acquisition": {
            "system": "NI cDAQ-9174",
            "modules": ["NI 9234 (4-channel IEPE, 24-bit)"],
            "sample_rate_hz": SAMPLE_RATE,
            "resolution_bits": 24,
            "anti_aliasing_filter_hz": 20000
        },
        "calibration": {
            "last_calibration_date": "2024-08-20",
            "calibration_lab": "Inspecta Nordic Oy",
            "calibration_certificate": "INS-2024-4471",
            "next_calibration_due": "2025-08-20"
        },
        "acoustic_environment": {
            "room_description": "Indoor pump room, ~8 m x 5 m, concrete floor and walls, no acoustic treatment",
            "background_noise_dba": 38,
            "dominant_background_sources": [
                "Water flow in pipes",
                "Building HVAC (switched off during measurements)"
            ],
            "notes": (
                "Ventilation fans and adjacent standby pump switched off during each session. "
                "Background noise floor measured at 38 dBA with pump stopped."
            )
        },
        "measurement_standard": (
            "ISO 10816-3: Mechanical vibration — Evaluation of machine vibration "
            "by measurements on non-rotating parts"
        )
    }
    _write_json(out_dir / "measurement_setup.json", measurement_setup)
    print("  Wrote background/measurement_setup.json")

    site_info = {
        "site_name": "Pirkanmaa Regional Water Treatment Plant – Pump Station 3",
        "operator": "Pirkanmaan Vesi Oy",
        "contact_person": "Markus Hämäläinen, Maintenance Engineer",
        "location": {
            "city": "Tampere",
            "country": "Finland",
            "coordinates_wgs84": {"lat": 61.4978, "lon": 23.7610}
        },
        "site_type": "Municipal water treatment and distribution",
        "pump_role": "Secondary distribution booster — feeds residential zone 3B (~850 households)",
        "operating_schedule": "Continuous 24/7, demand-controlled via downstream pressure sensor",
        "piping_layout": {
            "inlet_pipe_material": "Stainless steel AISI 316",
            "inlet_pipe_diameter_mm": 80,
            "outlet_pipe_diameter_mm": 65,
            "inlet_length_m": 4.2,
            "outlet_length_m": 12.0,
            "check_valve": True,
            "isolation_valves": 2,
            "flexible_connectors": True
        },
        "redundancy": {
            "standby_pump": "Identical CM5-6, serial GF-2021-CM5-00848",
            "standby_status": "Warm standby, auto-starts on primary failure"
        },
        "ambient_noise_sources": [
            "Adjacent standby CM5-6 pump (identical model, in standby during measurements)",
            "HVAC unit on roof (approx. 30 m away, switched off during measurements)",
            "Pipe flow noise (attenuated by flexible connectors and isolation flanges)",
            "Road traffic noise (building provides >25 dB attenuation)"
        ],
        "maintenance_history": [
            {
                "date": "2021-03-15",
                "action": "Initial installation and commissioning",
                "technician": "Pumppuhuolto Oy"
            },
            {
                "date": "2022-09-10",
                "action": "12-month routine inspection — no faults found, bearings greased",
                "technician": "M. Hämäläinen"
            },
            {
                "date": "2023-10-04",
                "action": "Mechanical seal replacement (normal wear), bearings OK",
                "technician": "Pumppuhuolto Oy / J. Korhonen"
            },
            {
                "date": "2024-08-20",
                "action": (
                    "Baseline condition monitoring campaign. All sensors calibrated. "
                    "Bearing temps normal (DE: 52.3°C), vibration 1.19 mm/s RMS. No anomalies."
                ),
                "technician": "J. Virtanen, NDT"
            }
        ]
    }
    _write_json(out_dir / "site_info.json", site_info)
    print("  Wrote background/site_info.json")


# ---------------------------------------------------------------------------
# SCADA / automation data
# ---------------------------------------------------------------------------
def generate_scada():
    print("\n[2/3] Generating SCADA time series...")
    out_dir = ROOT / "data" / "automation"
    out_dir.mkdir(parents=True, exist_ok=True)

    start_dt = datetime(2024, 9, 1, 0, 0, 0)
    end_dt   = datetime(2024, 12, 31, 23, 50, 0)
    step     = timedelta(minutes=10)

    timestamps = []
    ts = start_dt
    while ts <= end_dt:
        timestamps.append(ts)
        ts += step

    n_rows = len(timestamps)
    total_days = (end_dt - start_dt).days  # 122
    print(f"  Time range: {start_dt.date()} to {end_dt.date()}, 10-min intervals, {n_rows} rows")

    # Maintenance windows — pump stopped
    maint_windows = [
        (datetime(2024, 10, 8,  8,  0), datetime(2024, 10, 8,  14,  0)),
        (datetime(2024, 11, 19, 7,  0), datetime(2024, 11, 19, 11, 30)),
    ]

    fieldnames = [
        "timestamp", "pump_running", "rpm", "flow_rate_m3h",
        "pressure_inlet_bar", "pressure_outlet_bar",
        "temp_fluid_c", "temp_ambient_c",
        "temp_bearing_drive_end_c", "temp_bearing_non_drive_end_c",
        "vibration_overall_mms", "power_kw"
    ]

    rng = np.random.default_rng(SEED + 100)
    with open(out_dir / "scada_data.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for ts in timestamps:
            elapsed_days = (ts - start_dt).total_seconds() / 86400.0
            frac = elapsed_days / total_days  # 0 → 1
            in_maint = any(w_start <= ts <= w_end for w_start, w_end in maint_windows)
            running  = 0 if in_maint else 1

            hour_frac = ts.hour + ts.minute / 60.0
            # Seasonal ambient: ~8°C in Sep → ~−3°C in late Dec
            ambient = 8.0 - frac * 11.0 + 2.0 * math.sin(2 * math.pi * (hour_frac - 6) / 24)
            ambient += float(rng.normal(0, 0.5))

            if running:
                rpm  = float(np.clip(rng.normal(1450.0, 2.0), 1440.0, 1460.0))
                # Demand cycle: peaks 08:00 and 18:00, trough 03:00
                demand = 0.5 + 0.3 * (
                    math.sin(2 * math.pi * (hour_frac - 8) / 24) +
                    0.4 * math.sin(2 * math.pi * (hour_frac - 18) / 12)
                )
                demand = max(0.3, min(1.0, demand))
                flow   = float(np.clip(4.5 + demand * 5.0 + rng.normal(0, 0.3), 2.0, 10.5))
                p_in   = float(2.8 + rng.normal(0, 0.05))
                p_out  = float(5.2 + 0.1 * (8.5 - flow) + rng.normal(0, 0.03))
                t_fl   = float(ambient + 4.0 + rng.normal(0, 0.3))
                # Fault trend: 52 → 61 °C over 122 days
                t_de   = float(52.0 + frac * 9.0 + rng.normal(0, 0.4))
                t_nde  = float(48.0 + rng.normal(0, 0.3))
                # Vibration trend: 1.2 → 2.1 mm/s
                vib    = float(max(0.5, 1.2 + frac * 0.9 + rng.normal(0, 0.05)))
                power  = float(0.95 + 0.08 * flow + rng.normal(0, 0.02))
            else:
                rpm = flow = vib = power = 0.0
                p_in  = float(2.8 + rng.normal(0, 0.05))
                p_out = float(2.8 + rng.normal(0, 0.03))
                t_fl  = float(ambient + 2.0 + rng.normal(0, 0.2))
                t_de  = float(ambient + 1.0 + rng.normal(0, 0.2))
                t_nde = float(ambient + 0.8 + rng.normal(0, 0.2))

            writer.writerow({
                "timestamp":                    ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "pump_running":                 running,
                "rpm":                          round(rpm,   3),
                "flow_rate_m3h":                round(flow,  3),
                "pressure_inlet_bar":           round(p_in,  3),
                "pressure_outlet_bar":          round(p_out, 3),
                "temp_fluid_c":                 round(t_fl,  3),
                "temp_ambient_c":               round(ambient, 3),
                "temp_bearing_drive_end_c":     round(t_de,  3),
                "temp_bearing_non_drive_end_c": round(t_nde, 3),
                "vibration_overall_mms":        round(vib,   3),
                "power_kw":                     round(power, 3),
            })

    print("  Wrote data/automation/scada_data.csv")


# ---------------------------------------------------------------------------
# Acoustic measurement WAV files
# ---------------------------------------------------------------------------
def _pink_noise(n: int, rng: np.random.Generator, target_rms: float = 0.04) -> np.ndarray:
    """Generate pink (1/f) noise of length n with the given RMS."""
    white = rng.standard_normal(n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n)
    freqs[0] = 1.0          # avoid /0 at DC
    spectrum /= np.sqrt(freqs)
    spectrum[0] = 0.0       # zero DC
    pink = np.fft.irfft(spectrum, n=n)
    rms = np.sqrt(np.mean(pink ** 2))
    return pink * (target_rms / rms) if rms > 0 else pink


def _bearing_fault(
    t: np.ndarray,
    n: int,
    rng: np.random.Generator,
    bpfo_depth: float,
    bpfo_harmonics: int,
    sideband_amp: float,
) -> np.ndarray:
    """
    Synthesize bearing outer-race fault signal.

    Physical model:
      - Outer-race defect produces impacts at BPFO rate.
      - Each impact excites bearing-housing resonance (3–5 kHz carrier band).
      - Envelope = impulse train at BPFO with 5 ms exponential ring-down.
      - Fault signal = depth × carrier × (1 + envelope).
      - As fault develops: direct BPFO harmonics and shaft-BPFO sidebands appear.
    """
    if bpfo_depth == 0.0:
        return np.zeros(n)

    # Carrier: bandpass noise in bearing resonance band 3–5 kHz
    sos     = signal.butter(4, [3000, 5000], btype="bandpass", fs=SAMPLE_RATE, output="sos")
    carrier = signal.sosfilt(sos, rng.standard_normal(n))

    # Envelope: BPFO-rate impulse train convolved with ring-down kernel
    period_samp   = int(SAMPLE_RATE / BPFO)      # ≈ 551 samples
    envelope      = np.zeros(n)
    envelope[::period_samp] = 1.0
    decay_samp    = int(0.005 * SAMPLE_RATE)      # 5 ms = 240 samples
    decay_kernel  = np.exp(-np.arange(decay_samp) / max(1, decay_samp / 5))
    envelope      = signal.fftconvolve(envelope, decay_kernel, mode="full")[:n]
    if envelope.max() > 0:
        envelope /= envelope.max()

    fault = bpfo_depth * carrier * (1.0 + envelope)

    # Direct BPFO tonal harmonics (spectral lines at k × BPFO)
    for k in range(1, bpfo_harmonics + 1):
        amp   = (bpfo_depth * 0.3) / k
        phase = rng.uniform(0, 2 * np.pi)
        fault += amp * np.sin(2 * np.pi * k * BPFO * t + phase)

    # Sidebands around shaft harmonics at shaft_k ± BPFO
    if sideband_amp > 0.0:
        for k in range(1, 4):
            center = k * SHAFT_FREQ
            for sign in (-1, +1):
                sb_freq = center + sign * BPFO
                if sb_freq > 0:
                    phase = rng.uniform(0, 2 * np.pi)
                    fault += (sideband_amp / k) * np.sin(2 * np.pi * sb_freq * t + phase)

    return fault


def _synthesize_wav(
    rng: np.random.Generator,
    bpfo_depth: float,
    bpfo_harmonics: int,
    sideband_amp: float,
) -> np.ndarray:
    n = DURATION_S * SAMPLE_RATE
    t = np.linspace(0, DURATION_S, n, endpoint=False)
    audio = np.zeros(n, dtype=np.float64)

    audio += _pink_noise(n, rng, target_rms=0.04)

    # Shaft harmonics 1x–5x
    for k in range(1, 6):
        phase  = rng.uniform(0, 2 * np.pi)
        audio += (0.15 / k) * np.sin(2 * np.pi * k * SHAFT_FREQ * t + phase)

    # Blade pass 1x–2x
    for k in range(1, 3):
        phase  = rng.uniform(0, 2 * np.pi)
        audio += (0.08 / k) * np.sin(2 * np.pi * k * BPF * t + phase)

    # Motor electrical 100 Hz + 200 Hz
    for k in range(1, 3):
        phase  = rng.uniform(0, 2 * np.pi)
        audio += (0.06 / k) * np.sin(2 * np.pi * k * MOTOR_ELEC * t + phase)

    audio += _bearing_fault(t, n, rng, bpfo_depth, bpfo_harmonics, sideband_amp)

    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio * (0.9 / peak)
    return (audio * 32767).astype(np.int16)


def generate_acoustic():
    print("\n[3/3] Generating acoustic WAV files...")
    out_dir = ROOT / "data" / "acoustic"
    out_dir.mkdir(parents=True, exist_ok=True)

    sessions = [
        {
            "session_id":              1,
            "date":                    "2024-09-15",
            "time_start":              "09:32",
            "time_end":                "09:33",
            "operator":                "Janne Virtanen",
            "pump_running_hours":      2847,
            "ambient_temp_c":          7.8,
            "atmospheric_pressure_hpa": 1013.2,
            "fault_stage":             "Healthy",
            "notes": (
                "Baseline measurement. Pump in good condition per maintenance records. "
                "No audible anomalies. DE bearing temperature 52.9 °C (SCADA). "
                "Vibration 1.30 mm/s."
            ),
            "bpfo_depth":     0.000,
            "bpfo_harmonics": 0,
            "sideband_amp":   0.00,
        },
        {
            "session_id":              2,
            "date":                    "2024-10-17",
            "time_start":              "10:05",
            "time_end":                "10:06",
            "operator":                "Janne Virtanen",
            "pump_running_hours":      3567,
            "ambient_temp_c":          3.1,
            "atmospheric_pressure_hpa": 1007.8,
            "fault_stage":             "Incipient",
            "notes": (
                "Follow-up measurement. Slight DE bearing temperature increase noted "
                "in SCADA (~55.4 °C). Vibration 1.54 mm/s. No audible anomalies during "
                "inspection. Spectral analysis may reveal incipient BPFO activity."
            ),
            "bpfo_depth":     0.018,
            "bpfo_harmonics": 1,
            "sideband_amp":   0.00,
        },
        {
            "session_id":              3,
            "date":                    "2024-11-14",
            "time_start":              "09:55",
            "time_end":                "09:56",
            "operator":                "Janne Virtanen",
            "pump_running_hours":      4287,
            "ambient_temp_c":          -1.4,
            "atmospheric_pressure_hpa": 1021.5,
            "fault_stage":             "Developing",
            "notes": (
                "Condition monitoring check. DE bearing temperature trending up (SCADA: ~57.5 °C). "
                "Vibration 1.75 mm/s — above ISO 10816-3 zone A/B boundary. "
                "Faint periodic ticking audible near bearing housing on close inspection. "
                "Recommend increased monitoring frequency."
            ),
            "bpfo_depth":     0.120,
            "bpfo_harmonics": 2,
            "sideband_amp":   0.03,
        },
        {
            "session_id":              4,
            "date":                    "2024-12-12",
            "time_start":              "11:15",
            "time_end":                "11:16",
            "operator":                "Janne Virtanen",
            "pump_running_hours":      4967,
            "ambient_temp_c":          -5.2,
            "atmospheric_pressure_hpa": 1018.3,
            "fault_stage":             "Severe",
            "notes": (
                "Urgent inspection triggered by SCADA alert. DE bearing temperature 59.5 °C "
                "(alarm threshold 60 °C). Vibration 1.95 mm/s — ISO 10816-3 zone C. "
                "Clear repetitive impact sound audible at bearing housing. "
                "Multiple BPFO harmonics and sidebands expected in spectrum. "
                "Bearing replacement recommended immediately. Standby pump activated."
            ),
            "bpfo_depth":     0.450,
            "bpfo_harmonics": 3,
            "sideband_amp":   0.12,
        },
    ]

    known_freqs = {
        "bpfo_hz":       round(BPFO,       2),
        "bpfi_hz":       round(BPFI,       2),
        "bsf_hz":        round(BSF,        2),
        "ftf_hz":        round(FTF,        2),
        "shaft_1x_hz":   round(SHAFT_FREQ, 3),
        "blade_pass_hz": round(BPF,        2)
    }

    log_entries = []
    for s in sessions:
        wav_filename = f"acoustic_{s['date']}.wav"
        rng = np.random.default_rng(SEED + s["session_id"] * 17)
        depth_str = f"BPFO depth={s['bpfo_depth']}" if s["bpfo_depth"] > 0 else "healthy"
        print(f"  Session {s['session_id']} ({s['date']}): {s['fault_stage']} ({depth_str})...",
              end=" ", flush=True)
        audio = _synthesize_wav(rng, s["bpfo_depth"], s["bpfo_harmonics"], s["sideband_amp"])
        wavfile.write(str(out_dir / wav_filename), SAMPLE_RATE, audio)
        print(f"wrote {wav_filename}")

        log_entries.append({
            "session_id":              s["session_id"],
            "date":                    s["date"],
            "time_start":              s["time_start"],
            "time_end":                s["time_end"],
            "operator":                s["operator"],
            "pump_running_hours":      s["pump_running_hours"],
            "ambient_temp_c":          s["ambient_temp_c"],
            "atmospheric_pressure_hpa": s["atmospheric_pressure_hpa"],
            "fault_stage":             s["fault_stage"],
            "notes":                   s["notes"],
            "wav_file":                wav_filename,
            "sample_rate_hz":          SAMPLE_RATE,
            "duration_s":              DURATION_S,
            "known_fault_frequencies_hz": known_freqs,
        })

    _write_json(out_dir / "measurement_log.json", log_entries)
    print("  Wrote data/acoustic/measurement_log.json")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _write_json(path: Path, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
