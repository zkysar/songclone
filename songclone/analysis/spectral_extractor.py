"""Spectral and timbral analysis using librosa."""

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def analyze_spectral(audio_path: str, stem_name: str) -> dict[str, Any]:
    """Analyze spectral/timbral characteristics of a stem.

    Provides brightness, warmth, harmonic content, attack characteristics,
    and actionable EQ/synthesis suggestions.

    Args:
        audio_path: Path to the stem audio file (WAV).
        stem_name: Stem name (vocals, drums, bass, other) for context.

    Returns:
        dict with brightness_category, warmth_category, spectral_centroid_hz,
        harmonic_ratio, attack_time_ms, decay_character, eq_suggestions,
        synthesis_hints.
    """
    import librosa

    if not Path(audio_path).exists():
        return {"status": "error", "error_message": f"Audio file not found: {audio_path}"}

    try:
        y, sr = librosa.load(audio_path, sr=22050, duration=30)

        spectral_centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
        spectral_bandwidth = float(np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr)))
        spectral_rolloff = float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr)))
        spectral_flatness = float(np.mean(librosa.feature.spectral_flatness(y=y)))
        zero_crossing_rate = float(np.mean(librosa.feature.zero_crossing_rate(y)))

        harmonic, percussive = librosa.effects.hpss(y)
        harmonic_ratio = float(np.sum(np.abs(harmonic)) / (np.sum(np.abs(y)) + 1e-10))

        attack_time_ms = _estimate_attack_time(y, sr)
        decay_character = _estimate_decay_character(y, sr)

        brightness_category = _categorize_brightness(spectral_centroid, stem_name)
        warmth_category = _categorize_warmth(spectral_rolloff, spectral_flatness)

        eq_suggestions = _generate_eq_suggestions(
            stem_name, spectral_centroid, spectral_bandwidth,
            spectral_rolloff, warmth_category, brightness_category
        )

        synthesis_hints = _generate_synthesis_hints(
            stem_name, spectral_flatness, harmonic_ratio,
            attack_time_ms, spectral_centroid
        )

        return {
            "status": "success",
            "stem_name": stem_name,
            "brightness_category": brightness_category,
            "warmth_category": warmth_category,
            "spectral_centroid_hz": round(spectral_centroid, 1),
            "spectral_bandwidth_hz": round(spectral_bandwidth, 1),
            "spectral_rolloff_hz": round(spectral_rolloff, 1),
            "spectral_flatness": round(spectral_flatness, 4),
            "harmonic_ratio": round(harmonic_ratio, 2),
            "attack_time_ms": round(attack_time_ms, 1),
            "decay_character": decay_character,
            "eq_suggestions": eq_suggestions,
            "synthesis_hints": synthesis_hints,
        }

    except Exception as e:
        logger.error(f"Spectral analysis failed: {e}")
        return {"status": "error", "error_message": str(e)}


def _estimate_attack_time(y: np.ndarray, sr: int) -> float:
    """Estimate average attack time in milliseconds."""
    import librosa

    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="frames")
    if len(onset_frames) < 2:
        return 50.0

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    attack_times = []
    for onset in onset_frames[:10]:
        peak_idx = min(onset + 10, len(onset_env) - 1)
        if onset < len(onset_env):
            segment = onset_env[onset:peak_idx]
            if len(segment) > 0:
                peak_frame = onset + np.argmax(segment)
                attack_frames = peak_frame - onset
                attack_time_sec = librosa.frames_to_time(attack_frames, sr=sr)
                attack_times.append(attack_time_sec * 1000)

    return float(np.median(attack_times)) if attack_times else 50.0


def _estimate_decay_character(y: np.ndarray, sr: int) -> str:
    """Estimate decay character (sustained, short, plucky)."""
    import librosa

    rms = librosa.feature.rms(y=y)[0]
    if len(rms) < 10:
        return "unknown"

    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="frames")
    if len(onset_frames) == 0:
        return "sustained"

    decay_times = []
    hop_length = 512
    frame_duration = hop_length / sr

    for onset in onset_frames[:5]:
        if onset >= len(rms):
            continue

        peak_val = rms[onset]
        for i in range(onset, min(onset + 50, len(rms))):
            if rms[i] < peak_val * 0.5:
                decay_frames = i - onset
                decay_times.append(decay_frames * frame_duration * 1000)
                break
        else:
            decay_times.append(1000)

    avg_decay = np.median(decay_times) if decay_times else 500

    if avg_decay < 100:
        return "plucky"
    elif avg_decay < 400:
        return "short"
    else:
        return "sustained"


def _categorize_brightness(centroid: float, stem_name: str) -> str:
    """Categorize brightness based on spectral centroid."""
    thresholds = {
        "bass": {"dark": 300, "neutral": 600, "bright": 1000},
        "drums": {"dark": 1500, "neutral": 3000, "bright": 5000},
        "vocals": {"dark": 1000, "neutral": 2000, "bright": 3500},
        "other": {"dark": 1000, "neutral": 2500, "bright": 4000},
    }

    thresh = thresholds.get(stem_name, thresholds["other"])

    if centroid < thresh["dark"]:
        return "dark"
    elif centroid < thresh["neutral"]:
        return "neutral"
    elif centroid < thresh["bright"]:
        return "bright"
    else:
        return "very_bright"


def _categorize_warmth(rolloff: float, flatness: float) -> str:
    """Categorize warmth based on spectral rolloff and flatness."""
    if flatness > 0.3:
        return "cold"
    elif rolloff < 2000:
        return "warm"
    elif rolloff < 4000:
        return "neutral"
    else:
        return "cold"


def _generate_eq_suggestions(
    stem_name: str,
    centroid: float,
    bandwidth: float,
    rolloff: float,
    warmth: str,
    brightness: str,
) -> list[str]:
    """Generate actionable EQ suggestions."""
    suggestions = []

    if stem_name == "bass":
        if centroid < 200:
            suggestions.append("boost 2-3dB at 60-80Hz for sub presence")
        if centroid > 500:
            suggestions.append("cut 2-3dB around 400Hz to reduce muddiness")
        if warmth == "cold":
            suggestions.append("add subtle saturation for warmth")

    elif stem_name == "drums":
        if brightness == "dark":
            suggestions.append("boost 2dB at 5-8kHz for more air")
        if brightness == "very_bright":
            suggestions.append("cut 2dB at 8-10kHz to reduce harshness")
        suggestions.append("consider compression to control dynamics")

    elif stem_name == "vocals":
        if brightness == "dark":
            suggestions.append("boost 2dB at 3-4kHz for presence")
        if warmth == "cold":
            suggestions.append("boost 1dB around 200Hz for body")
        if brightness == "very_bright":
            suggestions.append("cut 2dB at 6-8kHz to reduce sibilance")

    elif stem_name == "other":
        if brightness == "very_bright":
            suggestions.append(f"LP filter around {int(rolloff * 0.8)}Hz to match warmth")
        if warmth == "warm" and brightness == "dark":
            suggestions.append("consider adding subtle high-shelf boost at 8kHz")
        if centroid > 3000:
            suggestions.append("cut 2dB around 2-3kHz if harsh")

    if not suggestions:
        suggestions.append("EQ balance appears appropriate")

    return suggestions[:3]


def _generate_synthesis_hints(
    stem_name: str,
    flatness: float,
    harmonic_ratio: float,
    attack_ms: float,
    centroid: float,
) -> list[str]:
    """Generate synthesis parameter hints."""
    hints = []

    if flatness > 0.3:
        hints.append("use noise or FM synthesis for texture")
    elif flatness < 0.1:
        hints.append("use pure harmonic waveforms (saw, square)")
    else:
        hints.append("blend harmonic oscillators with subtle noise")

    if harmonic_ratio > 0.8:
        hints.append("emphasize harmonic content over percussive")
    elif harmonic_ratio < 0.4:
        hints.append("add percussive transient shaping")

    if attack_ms < 20:
        hints.append("set fast attack (< 10ms)")
    elif attack_ms > 100:
        hints.append("set slow attack (> 50ms) for swell")
    else:
        hints.append(f"set attack around {int(attack_ms)}ms")

    if centroid < 1500:
        hints.append(f"LP filter around {int(centroid * 2)}Hz")
    elif centroid > 3000:
        hints.append("keep filter open or use HP for brightness")

    return hints[:4]
