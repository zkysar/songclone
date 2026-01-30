"""Instrument classification using Essentia TensorFlow models."""

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

VST_MAPPING = {
    "electric_piano": {"vst": "Dexed", "preset_category": "electric_piano"},
    "acoustic_piano": {"vst": "Vital", "preset_category": "piano"},
    "synth_lead": {"vst": "Vital", "preset_category": "lead"},
    "synth_pad": {"vst": "Vital", "preset_category": "pad"},
    "synth_bass": {"vst": "Vital", "preset_category": "bass"},
    "acoustic_bass": {"vst": "Vital", "preset_category": "bass"},
    "electric_bass": {"vst": "Vital", "preset_category": "bass"},
    "electric_guitar": {"vst": "Vital", "preset_category": "pluck"},
    "acoustic_guitar": {"vst": "Vital", "preset_category": "pluck"},
    "strings": {"vst": "Vital", "preset_category": "strings"},
    "brass": {"vst": "Vital", "preset_category": "brass"},
    "organ": {"vst": "Dexed", "preset_category": "organ"},
    "drums": {"vst": "ReaSamplOmatic5000", "preset_category": "kit"},
    "percussion": {"vst": "ReaSamplOmatic5000", "preset_category": "percussion"},
    "vocals": {"vst": "Vital", "preset_category": "lead"},
    "unknown": {"vst": "ReaSynth", "preset_category": "init"},
}

TIMBRE_DESCRIPTORS = {
    "electric_piano": ["warm", "mellow", "bell-like", "round"],
    "acoustic_piano": ["bright", "percussive", "resonant", "natural"],
    "synth_lead": ["bright", "cutting", "synthetic", "sharp"],
    "synth_pad": ["soft", "warm", "atmospheric", "evolving"],
    "synth_bass": ["deep", "punchy", "synthetic", "heavy"],
    "acoustic_bass": ["warm", "woody", "natural", "round"],
    "electric_bass": ["punchy", "defined", "growling", "solid"],
    "electric_guitar": ["bright", "distorted", "sustaining", "aggressive"],
    "acoustic_guitar": ["warm", "natural", "plucky", "resonant"],
    "strings": ["lush", "sustained", "rich", "orchestral"],
    "brass": ["bright", "brassy", "powerful", "bold"],
    "organ": ["warm", "sustained", "rich", "rotary"],
}


def analyze_instrument(audio_path: str, stem_name: str) -> dict[str, Any]:
    """Identify the instrument type in a stem.

    Uses Essentia's pre-trained instrument classification models.
    Falls back to spectral-based heuristics if models are unavailable.

    Args:
        audio_path: Path to the stem audio file (WAV).
        stem_name: Stem name (vocals, drums, bass, other) for context.

    Returns:
        dict with primary_instrument, confidence, secondary_instruments,
        timbre_descriptors, is_synthetic, suggested_vst, suggested_preset_category.
    """
    if not Path(audio_path).exists():
        return {"status": "error", "error_message": f"Audio file not found: {audio_path}"}

    try:
        return _essentia_instrument_analysis(audio_path, stem_name)
    except Exception as e:
        logger.warning(f"Essentia instrument analysis failed: {e}, using librosa fallback")
        return _librosa_instrument_fallback(audio_path, stem_name)


def _essentia_instrument_analysis(audio_path: str, stem_name: str) -> dict[str, Any]:
    """Instrument analysis using Essentia TensorFlow models."""
    try:
        from essentia.standard import MonoLoader, TensorflowPredictEffnetDiscogs
    except ImportError:
        raise RuntimeError("essentia-tensorflow not installed")

    audio = MonoLoader(filename=audio_path, sampleRate=16000)()

    model_path = _get_model_path("mtg_jamendo_instrument-discogs-effnet-1")
    if not model_path.exists():
        raise RuntimeError(f"Instrument model not found at {model_path}")

    model = TensorflowPredictEffnetDiscogs(
        graphFilename=str(model_path),
        output="model/Softmax",
    )
    predictions = model(audio)
    mean_predictions = np.mean(predictions, axis=0)

    instruments = _get_instrument_labels()
    ranked = sorted(
        zip(instruments, mean_predictions),
        key=lambda x: x[1],
        reverse=True,
    )

    primary = ranked[0][0]
    confidence = float(ranked[0][1])
    secondary = [inst for inst, _ in ranked[1:4] if _ > 0.1]

    primary = _refine_with_stem_context(primary, stem_name)
    is_synthetic = _is_synthetic_sound(primary, audio)
    timbre = TIMBRE_DESCRIPTORS.get(primary, ["unknown"])
    vst_info = VST_MAPPING.get(primary, VST_MAPPING["unknown"])

    return {
        "status": "success",
        "stem_name": stem_name,
        "primary_instrument": primary,
        "confidence": round(confidence, 2),
        "secondary_instruments": secondary,
        "timbre_descriptors": timbre[:3],
        "is_synthetic": is_synthetic,
        "suggested_vst": vst_info["vst"],
        "suggested_preset_category": vst_info["preset_category"],
    }


def _librosa_instrument_fallback(audio_path: str, stem_name: str) -> dict[str, Any]:
    """Fallback instrument analysis using librosa spectral features."""
    import librosa

    y, sr = librosa.load(audio_path, sr=22050, duration=30)

    spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
    spectral_bandwidth = np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr))
    spectral_flatness = np.mean(librosa.feature.spectral_flatness(y=y))
    zero_crossing_rate = np.mean(librosa.feature.zero_crossing_rate(y))
    rms = np.mean(librosa.feature.rms(y=y))

    onsets = librosa.onset.onset_detect(y=y, sr=sr)
    attack_sharpness = len(onsets) / (len(y) / sr) if len(y) > 0 else 0

    primary = _heuristic_instrument_from_features(
        stem_name, spectral_centroid, spectral_bandwidth,
        spectral_flatness, zero_crossing_rate, attack_sharpness
    )

    is_synthetic = bool(spectral_flatness > 0.3)
    timbre = TIMBRE_DESCRIPTORS.get(primary, ["unknown"])
    vst_info = VST_MAPPING.get(primary, VST_MAPPING["unknown"])

    secondary = _get_secondary_instruments(primary, stem_name)

    return {
        "status": "success",
        "stem_name": stem_name,
        "primary_instrument": primary,
        "confidence": 0.5,
        "secondary_instruments": secondary,
        "timbre_descriptors": timbre[:3],
        "is_synthetic": is_synthetic,
        "suggested_vst": vst_info["vst"],
        "suggested_preset_category": vst_info["preset_category"],
        "fallback": True,
    }


def _get_model_path(model_name: str) -> Path:
    """Get path to Essentia model file."""
    essentia_models_dir = Path.home() / ".essentia" / "models"
    return essentia_models_dir / f"{model_name}.pb"


def _get_instrument_labels() -> list[str]:
    """Get instrument labels for the classifier."""
    return [
        "acoustic_piano", "electric_piano", "organ",
        "acoustic_guitar", "electric_guitar",
        "acoustic_bass", "electric_bass", "synth_bass",
        "strings", "brass", "woodwind",
        "synth_lead", "synth_pad",
        "drums", "percussion",
        "vocals",
    ]


def _refine_with_stem_context(instrument: str, stem_name: str) -> str:
    """Refine instrument prediction using stem context."""
    stem_instrument_map = {
        "vocals": ["vocals", "synth_lead"],
        "drums": ["drums", "percussion"],
        "bass": ["acoustic_bass", "electric_bass", "synth_bass"],
        "other": None,
    }

    expected = stem_instrument_map.get(stem_name)
    if expected and instrument not in expected:
        if stem_name == "bass":
            return "synth_bass"
        elif stem_name == "drums":
            return "drums"
        elif stem_name == "vocals":
            return "vocals"

    return instrument


def _is_synthetic_sound(instrument: str, audio: np.ndarray) -> bool:
    """Determine if the sound is synthetic vs acoustic."""
    synthetic_instruments = ["synth_lead", "synth_pad", "synth_bass", "electric_piano"]
    return instrument in synthetic_instruments


def _heuristic_instrument_from_features(
    stem_name: str,
    centroid: float,
    bandwidth: float,
    flatness: float,
    zcr: float,
    attack_sharpness: float,
) -> str:
    """Heuristically determine instrument from spectral features."""
    if stem_name == "bass":
        if flatness > 0.2:
            return "synth_bass"
        elif centroid < 500:
            return "acoustic_bass"
        else:
            return "electric_bass"

    elif stem_name == "drums":
        return "drums"

    elif stem_name == "vocals":
        return "vocals"

    elif stem_name == "other":
        if flatness > 0.3 and bandwidth > 2000:
            return "synth_pad"
        elif centroid > 2000 and attack_sharpness > 5:
            return "synth_lead"
        elif centroid < 1500 and zcr < 0.1:
            return "electric_piano"
        elif attack_sharpness > 8:
            return "acoustic_piano"
        elif bandwidth > 3000:
            return "strings"
        else:
            return "synth_pad"

    return "unknown"


def _get_secondary_instruments(primary: str, stem_name: str) -> list[str]:
    """Get likely secondary instruments based on primary and stem."""
    secondary_map = {
        "electric_piano": ["synth_pad", "organ"],
        "synth_pad": ["strings", "synth_lead"],
        "synth_lead": ["synth_pad", "electric_piano"],
        "synth_bass": ["electric_bass"],
        "acoustic_bass": ["electric_bass"],
        "electric_guitar": ["acoustic_guitar"],
    }
    return secondary_map.get(primary, [])
