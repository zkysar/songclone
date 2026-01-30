"""Effects and mix analysis using librosa and custom algorithms."""

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def analyze_effects(audio_path: str) -> dict[str, Any]:
    """Analyze reverb, compression, and EQ characteristics.

    Provides specific parameter suggestions for ReaVerb, ReaComp, ReaEQ
    based on the detected characteristics of the original audio.

    Args:
        audio_path: Path to the audio file (WAV).

    Returns:
        dict with reverb (RT60, room_size, wet_dry), compression (ratio, attack),
        eq_profile (centroid, bass_energy, suggested_bands).
    """
    import librosa

    if not Path(audio_path).exists():
        return {"status": "error", "error_message": f"Audio file not found: {audio_path}"}

    try:
        y, sr = librosa.load(audio_path, sr=22050)

        reverb_analysis = _analyze_reverb(y, sr)
        compression_analysis = _analyze_compression(y, sr)
        eq_profile = _analyze_eq_profile(y, sr)

        return {
            "status": "success",
            "reverb": reverb_analysis,
            "compression": compression_analysis,
            "eq_profile": eq_profile,
        }

    except Exception as e:
        logger.error(f"Effects analysis failed: {e}")
        return {"status": "error", "error_message": str(e)}


def _analyze_reverb(y: np.ndarray, sr: int) -> dict[str, Any]:
    """Analyze reverb characteristics."""
    import librosa

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="frames")

    if len(onset_frames) < 3:
        return {
            "estimated_rt60": 0.5,
            "room_size": "small",
            "wet_dry_ratio": 0.1,
            "suggested_reaverb_settings": {"decay": 0.5, "wet": -18, "dry": 0},
        }

    decay_times = []
    hop_length = 512

    for onset in onset_frames[:10]:
        if onset + 50 >= len(onset_env):
            continue

        peak_val = onset_env[onset]
        decay_start = onset_env[onset]

        for i in range(onset, min(onset + 100, len(onset_env))):
            if onset_env[i] < decay_start * 0.001:
                decay_frames = i - onset
                decay_time = librosa.frames_to_time(decay_frames, sr=sr, hop_length=hop_length)
                decay_times.append(decay_time)
                break

    if decay_times:
        rt60_estimate = float(np.median(decay_times))
    else:
        rt60_estimate = 0.5

    spectral_flux = np.mean(np.abs(np.diff(librosa.feature.spectral_centroid(y=y, sr=sr))))
    if spectral_flux < 50:
        diffusion = "high"
    else:
        diffusion = "low"

    if rt60_estimate < 0.3:
        room_size = "small"
        wet_dry = 0.1
    elif rt60_estimate < 0.8:
        room_size = "medium"
        wet_dry = 0.2
    elif rt60_estimate < 1.5:
        room_size = "large"
        wet_dry = 0.3
    else:
        room_size = "hall"
        wet_dry = 0.4

    wet_db = -18 + (wet_dry * 20)

    return {
        "estimated_rt60": round(rt60_estimate, 2),
        "room_size": room_size,
        "wet_dry_ratio": round(wet_dry, 2),
        "diffusion": diffusion,
        "suggested_reaverb_settings": {
            "decay": round(rt60_estimate, 1),
            "wet": round(wet_db, 0),
            "dry": 0,
        },
    }


def _analyze_compression(y: np.ndarray, sr: int) -> dict[str, Any]:
    """Analyze compression characteristics."""
    import librosa

    rms = librosa.feature.rms(y=y)[0]

    rms_db = 20 * np.log10(rms + 1e-10)
    dynamic_range = float(np.max(rms_db) - np.min(rms_db))

    peak = np.max(np.abs(y))
    rms_total = np.sqrt(np.mean(y**2))
    crest_factor = float(20 * np.log10(peak / (rms_total + 1e-10)))

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="frames")

    attack_times = []
    hop_length = 512
    for onset in onset_frames[:10]:
        if onset + 10 >= len(onset_env):
            continue
        peak_idx = onset + np.argmax(onset_env[onset:onset+10])
        attack_frames = peak_idx - onset
        attack_time = librosa.frames_to_time(attack_frames, sr=sr, hop_length=hop_length)
        attack_times.append(attack_time * 1000)

    avg_attack = float(np.median(attack_times)) if attack_times else 20.0

    if dynamic_range < 10:
        estimated_ratio = 8.0
        compression_amount = "heavy"
    elif dynamic_range < 15:
        estimated_ratio = 4.0
        compression_amount = "moderate"
    elif dynamic_range < 25:
        estimated_ratio = 2.0
        compression_amount = "light"
    else:
        estimated_ratio = 1.0
        compression_amount = "none"

    if avg_attack < 10:
        attack_character = "fast"
        suggested_attack = 5
    elif avg_attack < 30:
        attack_character = "medium"
        suggested_attack = 15
    else:
        attack_character = "slow"
        suggested_attack = 30

    if dynamic_range < 15:
        suggested_release = 150
    else:
        suggested_release = 100

    threshold = -18 if compression_amount in ["heavy", "moderate"] else -24

    return {
        "dynamic_range_db": round(dynamic_range, 1),
        "crest_factor": round(crest_factor, 1),
        "estimated_ratio": estimated_ratio,
        "compression_amount": compression_amount,
        "attack_character": attack_character,
        "suggested_reacomp_settings": {
            "ratio": estimated_ratio,
            "attack": suggested_attack,
            "release": suggested_release,
            "threshold": threshold,
        },
    }


def _analyze_eq_profile(y: np.ndarray, sr: int) -> dict[str, Any]:
    """Analyze EQ profile and suggest ReaEQ bands."""
    import librosa

    spectral_centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))

    S = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)

    sub_mask = freqs < 80
    bass_mask = (freqs >= 80) & (freqs < 250)
    low_mid_mask = (freqs >= 250) & (freqs < 500)
    mid_mask = (freqs >= 500) & (freqs < 2000)
    presence_mask = (freqs >= 2000) & (freqs < 6000)
    air_mask = freqs >= 6000

    def band_energy(mask: np.ndarray) -> float:
        if not np.any(mask):
            return -60.0
        band_power = np.mean(S[mask, :])
        return float(20 * np.log10(band_power + 1e-10))

    sub_energy = band_energy(sub_mask)
    bass_energy = band_energy(bass_mask)
    low_mid_energy = band_energy(low_mid_mask)
    mid_energy = band_energy(mid_mask)
    presence_energy = band_energy(presence_mask)
    air_energy = band_energy(air_mask)

    reference = mid_energy
    relative_bass = bass_energy - reference
    relative_presence = presence_energy - reference
    relative_air = air_energy - reference

    suggested_bands = []

    if relative_bass < -6:
        suggested_bands.append({
            "freq": 80,
            "gain": min(6, abs(relative_bass) / 2),
            "q": 1.0,
            "type": "lowshelf",
        })
    elif relative_bass > 3:
        suggested_bands.append({
            "freq": 80,
            "gain": -min(6, relative_bass / 2),
            "q": 1.0,
            "type": "lowshelf",
        })

    if low_mid_energy > mid_energy + 3:
        suggested_bands.append({
            "freq": 350,
            "gain": -3,
            "q": 2.0,
            "type": "peak",
        })

    if relative_presence < -6:
        suggested_bands.append({
            "freq": 3000,
            "gain": min(4, abs(relative_presence) / 2),
            "q": 1.5,
            "type": "peak",
        })
    elif relative_presence > 6:
        suggested_bands.append({
            "freq": 3000,
            "gain": -min(4, relative_presence / 2),
            "q": 1.5,
            "type": "peak",
        })

    if relative_air < -10:
        suggested_bands.append({
            "freq": 10000,
            "gain": min(4, abs(relative_air) / 3),
            "q": 0.7,
            "type": "highshelf",
        })

    if not suggested_bands:
        suggested_bands.append({
            "freq": 1000,
            "gain": 0,
            "q": 1.0,
            "type": "peak",
        })

    return {
        "spectral_centroid_hz": round(spectral_centroid, 0),
        "bass_energy_db": round(relative_bass, 1),
        "presence_energy_db": round(relative_presence, 1),
        "air_energy_db": round(relative_air, 1),
        "balance": _classify_balance(relative_bass, relative_presence),
        "suggested_reaeq_bands": suggested_bands[:4],
    }


def _classify_balance(bass_rel: float, presence_rel: float) -> str:
    """Classify overall tonal balance."""
    if bass_rel > 3 and presence_rel < -3:
        return "warm/dark"
    elif bass_rel < -3 and presence_rel > 3:
        return "bright/thin"
    elif bass_rel > 3 and presence_rel > 3:
        return "scooped"
    elif bass_rel < -3 and presence_rel < -3:
        return "mid-heavy"
    else:
        return "balanced"
