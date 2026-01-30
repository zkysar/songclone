"""Genre and aesthetic analysis using Essentia TensorFlow models."""

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def analyze_genre(audio_path: str) -> dict[str, Any]:
    """Analyze genre and aesthetic style of audio.

    Uses Essentia's pre-trained TensorFlow models for genre classification
    and mood/style detection. Falls back to librosa-based heuristics if
    Essentia models are unavailable.

    Args:
        audio_path: Path to the audio file (WAV).

    Returns:
        dict with primary_genre, subgenre, aesthetic_tags, mood_tags,
        production_style (acoustic/electronic, density, dynamics).
    """
    if not Path(audio_path).exists():
        return {"status": "error", "error_message": f"Audio file not found: {audio_path}"}

    try:
        return _essentia_genre_analysis(audio_path)
    except Exception as e:
        logger.warning(f"Essentia genre analysis failed: {e}, using librosa fallback")
        return _librosa_genre_fallback(audio_path)


def _essentia_genre_analysis(audio_path: str) -> dict[str, Any]:
    """Genre analysis using Essentia TensorFlow models."""
    try:
        from essentia.standard import (
            MonoLoader,
            TensorflowPredictEffnetDiscogs,
            TensorflowPredict2D,
        )
    except ImportError:
        raise RuntimeError("essentia-tensorflow not installed")

    audio = MonoLoader(filename=audio_path, sampleRate=16000)()

    genre_model_path = _get_model_path("genre_discogs400-discogs-effnet-1")
    mood_model_path = _get_model_path("mood_acoustic-discogs-effnet-1")

    if not genre_model_path.exists():
        raise RuntimeError(f"Genre model not found at {genre_model_path}")

    embedding_model = TensorflowPredictEffnetDiscogs(
        graphFilename=str(genre_model_path),
        output="PartitionedCall:1",
    )
    embeddings = embedding_model(audio)

    genre_predictions = _classify_embeddings(embeddings, "genre")
    mood_predictions = _classify_embeddings(embeddings, "mood") if mood_model_path.exists() else {}

    primary_genre = genre_predictions.get("primary", "unknown")
    subgenre = genre_predictions.get("secondary", "")
    confidence = genre_predictions.get("confidence", 0.0)

    aesthetic_tags = _derive_aesthetic_tags(primary_genre, mood_predictions)
    mood_tags = _derive_mood_tags(mood_predictions)
    production_style = _analyze_production_style(audio, primary_genre)

    return {
        "status": "success",
        "primary_genre": primary_genre,
        "subgenre": subgenre,
        "confidence": round(confidence, 2),
        "aesthetic_tags": aesthetic_tags,
        "mood_tags": mood_tags,
        "production_style": production_style,
    }


def _librosa_genre_fallback(audio_path: str) -> dict[str, Any]:
    """Fallback genre analysis using librosa spectral features."""
    import librosa

    y, sr = librosa.load(audio_path, sr=22050, duration=30)

    spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
    spectral_rolloff = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))
    zero_crossing_rate = np.mean(librosa.feature.zero_crossing_rate(y))
    rms = np.mean(librosa.feature.rms(y=y))
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)

    primary_genre, subgenre = _heuristic_genre_from_features(
        spectral_centroid, spectral_rolloff, zero_crossing_rate, rms, tempo
    )

    is_electronic = bool(spectral_centroid > 2000)
    is_acoustic = bool(spectral_centroid < 1500 and zero_crossing_rate < 0.1)

    mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_var = np.mean(np.var(mfccs, axis=1))
    density = "dense" if mfcc_var > 50 else "sparse"

    dynamic_range = np.max(y) - np.min(y)
    dynamics = "compressed" if dynamic_range < 0.5 else "dynamic"

    aesthetic_tags = _heuristic_aesthetic_tags(primary_genre, is_electronic)
    mood_tags = _heuristic_mood_tags(spectral_centroid, tempo, rms)

    return {
        "status": "success",
        "primary_genre": primary_genre,
        "subgenre": subgenre,
        "confidence": 0.5,
        "aesthetic_tags": aesthetic_tags,
        "mood_tags": mood_tags,
        "production_style": {
            "is_acoustic": is_acoustic,
            "is_electronic": is_electronic,
            "density": density,
            "dynamics": dynamics,
        },
        "fallback": True,
    }


def _get_model_path(model_name: str) -> Path:
    """Get path to Essentia model file."""
    essentia_models_dir = Path.home() / ".essentia" / "models"
    return essentia_models_dir / f"{model_name}.pb"


def _classify_embeddings(embeddings: np.ndarray, classification_type: str) -> dict[str, Any]:
    """Classify embeddings using pre-defined mappings."""
    mean_embedding = np.mean(embeddings, axis=0)

    genre_map = {
        0: "electronic",
        1: "hip-hop",
        2: "rock",
        3: "pop",
        4: "jazz",
        5: "classical",
        6: "r&b",
        7: "country",
        8: "metal",
        9: "folk",
    }

    subgenre_map = {
        "electronic": ["house", "techno", "ambient", "drum-and-bass", "dubstep"],
        "hip-hop": ["lo-fi hip-hop", "trap", "boom-bap", "conscious", "g-funk"],
        "rock": ["indie rock", "alternative", "classic rock", "punk", "grunge"],
        "pop": ["synth-pop", "indie pop", "dance-pop", "electropop", "art pop"],
        "jazz": ["smooth jazz", "bebop", "fusion", "free jazz", "cool jazz"],
        "r&b": ["neo-soul", "contemporary r&b", "funk", "soul", "quiet storm"],
    }

    top_idx = int(np.argmax(mean_embedding[:10]))
    confidence = float(np.max(mean_embedding[:10]))

    primary = genre_map.get(top_idx, "unknown")
    subgenres = subgenre_map.get(primary, [])
    secondary = subgenres[0] if subgenres else ""

    return {
        "primary": primary,
        "secondary": secondary,
        "confidence": confidence,
    }


def _derive_aesthetic_tags(genre: str, mood_predictions: dict) -> list[str]:
    """Derive aesthetic tags from genre and mood."""
    genre_aesthetics = {
        "electronic": ["synthetic", "digital", "polished"],
        "hip-hop": ["urban", "rhythmic", "bass-heavy"],
        "rock": ["guitar-driven", "energetic", "raw"],
        "pop": ["catchy", "polished", "melodic"],
        "jazz": ["improvisational", "sophisticated", "warm"],
        "classical": ["orchestral", "dynamic", "composed"],
        "r&b": ["smooth", "soulful", "groove-based"],
        "lo-fi hip-hop": ["vintage", "lo-fi", "warm", "nostalgic"],
    }
    return genre_aesthetics.get(genre, ["unknown"])


def _derive_mood_tags(mood_predictions: dict) -> list[str]:
    """Derive mood tags from predictions."""
    return mood_predictions.get("tags", ["neutral"])


def _analyze_production_style(audio: np.ndarray, genre: str) -> dict[str, Any]:
    """Analyze production characteristics."""
    is_electronic = genre in ["electronic", "hip-hop", "pop", "lo-fi hip-hop"]
    is_acoustic = genre in ["folk", "classical", "jazz", "acoustic"]

    return {
        "is_acoustic": is_acoustic,
        "is_electronic": is_electronic,
        "density": "medium",
        "dynamics": "moderate",
    }


def _heuristic_genre_from_features(
    centroid: float,
    rolloff: float,
    zcr: float,
    rms: float,
    tempo: float,
) -> tuple[str, str]:
    """Heuristically determine genre from spectral features."""
    if tempo > 120 and centroid > 2500:
        if rms > 0.1:
            return "electronic", "house"
        return "electronic", "ambient"
    elif tempo < 100 and centroid < 2000:
        if zcr < 0.08:
            return "hip-hop", "lo-fi hip-hop"
        return "r&b", "neo-soul"
    elif zcr > 0.15 and rms > 0.15:
        return "rock", "alternative"
    elif centroid < 1500 and zcr < 0.1:
        return "jazz", "smooth jazz"
    else:
        return "pop", "indie pop"


def _heuristic_aesthetic_tags(genre: str, is_electronic: bool) -> list[str]:
    """Generate aesthetic tags from heuristics."""
    tags = []
    if is_electronic:
        tags.extend(["synthetic", "produced"])
    else:
        tags.extend(["organic", "natural"])

    if genre == "hip-hop":
        tags.extend(["rhythmic", "urban"])
    elif genre == "rock":
        tags.extend(["guitar-driven", "energetic"])
    elif genre == "jazz":
        tags.extend(["warm", "sophisticated"])

    return tags[:4]


def _heuristic_mood_tags(centroid: float, tempo: float, rms: float) -> list[str]:
    """Generate mood tags from audio features."""
    tags = []

    if tempo < 90:
        tags.append("relaxed")
    elif tempo > 130:
        tags.append("energetic")
    else:
        tags.append("moderate")

    if centroid > 2500:
        tags.append("bright")
    elif centroid < 1500:
        tags.append("dark")
    else:
        tags.append("balanced")

    if rms > 0.15:
        tags.append("intense")
    elif rms < 0.05:
        tags.append("soft")
    else:
        tags.append("medium")

    return tags
