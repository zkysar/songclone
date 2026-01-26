"""Chord and key detection using librosa."""

import asyncio
import logging
from pathlib import Path

import numpy as np

from songclone.analysis.schemas import ChordEvent

logger = logging.getLogger(__name__)

CHORD_TEMPLATES = {
    "C": [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0],
    "Cm": [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0],
    "C#": [0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0],
    "C#m": [0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
    "D": [0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0],
    "Dm": [0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0],
    "D#": [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0],
    "D#m": [0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0],
    "E": [0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1],
    "Em": [0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1],
    "F": [1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0],
    "Fm": [1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0],
    "F#": [0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0],
    "F#m": [0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0],
    "G": [0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1],
    "Gm": [0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0],
    "G#": [1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0],
    "G#m": [0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1],
    "A": [0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
    "Am": [1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
    "A#": [0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0],
    "A#m": [0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0],
    "B": [0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1],
    "Bm": [0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1],
}

KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


async def detect_chords(
    audio_path: Path,
    hop_length: int = 512,
    min_duration: float = 0.5,
) -> list[ChordEvent]:
    """
    Detect chord progressions using librosa chroma features.

    Args:
        audio_path: Path to input audio file
        hop_length: Hop length for analysis
        min_duration: Minimum chord duration in seconds

    Returns:
        List of ChordEvent with timestamps and chord symbols
    """
    logger.info(f"Detecting chords in {audio_path}")

    try:
        import librosa

        y, sr = librosa.load(str(audio_path))

        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)

        frame_duration = hop_length / sr
        n_frames = chroma.shape[1]

        chords: list[ChordEvent] = []
        current_chord = None
        chord_start = 0.0

        for i in range(n_frames):
            frame_chroma = chroma[:, i]
            detected_chord = _match_chord(frame_chroma)

            if detected_chord != current_chord:
                if current_chord is not None:
                    duration = (i * frame_duration) - chord_start
                    if duration >= min_duration:
                        chords.append(ChordEvent(
                            time=chord_start,
                            duration=duration,
                            chord=current_chord,
                        ))

                current_chord = detected_chord
                chord_start = i * frame_duration

        if current_chord is not None:
            duration = (n_frames * frame_duration) - chord_start
            if duration >= min_duration:
                chords.append(ChordEvent(
                    time=chord_start,
                    duration=duration,
                    chord=current_chord,
                ))

        logger.info(f"Detected {len(chords)} chords in {audio_path}")
        return chords

    except ImportError:
        logger.warning("librosa not available for chord detection")
        return []
    except Exception as e:
        logger.error(f"Chord detection failed: {e}")
        return []


def _match_chord(chroma: np.ndarray) -> str:
    """Match a chroma vector to the closest chord template."""
    best_chord = "C"
    best_score = -1

    chroma_normalized = chroma / (np.linalg.norm(chroma) + 1e-8)

    for chord_name, template in CHORD_TEMPLATES.items():
        template_array = np.array(template, dtype=float)
        template_normalized = template_array / (np.linalg.norm(template_array) + 1e-8)

        score = np.dot(chroma_normalized, template_normalized)

        if score > best_score:
            best_score = score
            best_chord = chord_name

    return best_chord


async def detect_key(audio_path: Path) -> str:
    """
    Detect musical key using librosa.

    Args:
        audio_path: Path to input audio file

    Returns:
        Key string, e.g., "C major", "A minor"
    """
    logger.info(f"Detecting key of {audio_path}")

    try:
        import librosa

        y, sr = librosa.load(str(audio_path))

        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = np.mean(chroma, axis=1)

        major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

        best_key = "C major"
        best_correlation = -1

        for shift in range(12):
            shifted_chroma = np.roll(chroma_mean, -shift)

            major_corr = np.corrcoef(shifted_chroma, major_profile)[0, 1]
            if major_corr > best_correlation:
                best_correlation = major_corr
                best_key = f"{KEY_NAMES[shift]} major"

            minor_corr = np.corrcoef(shifted_chroma, minor_profile)[0, 1]
            if minor_corr > best_correlation:
                best_correlation = minor_corr
                best_key = f"{KEY_NAMES[shift]} minor"

        logger.info(f"Detected key: {best_key}")
        return best_key

    except ImportError:
        logger.warning("librosa not available for key detection")
        return "C major"
    except Exception as e:
        logger.error(f"Key detection failed: {e}")
        return "C major"
