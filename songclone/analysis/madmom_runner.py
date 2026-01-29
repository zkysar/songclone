"""Beat and tempo detection using madmom."""

import asyncio
import logging
from pathlib import Path
from typing import NamedTuple

import librosa
import numpy as np
from madmom.features.beats import DBNBeatTrackingProcessor, RNNBeatProcessor
from madmom.features.downbeats import DBNDownBeatTrackingProcessor, RNNDownBeatProcessor

logger = logging.getLogger(__name__)


class BeatInfo(NamedTuple):
    """Beat tracking results."""

    tempo_bpm: float
    time_signature: str
    beats: list[float]
    downbeats: list[float]


def _run_madmom_sync(audio_path: Path) -> BeatInfo:
    """Synchronous madmom beat detection (CPU-intensive)."""
    print(f"=== _run_madmom_sync ENTERED ===", flush=True)
    print(f"=== madmom: creating RNNBeatProcessor ===", flush=True)
    beat_proc = RNNBeatProcessor()
    print(f"=== madmom: RNNBeatProcessor created, processing audio ===", flush=True)
    beat_act = beat_proc(str(audio_path))
    print(f"=== madmom: beat activations done ===", flush=True)

    print(f"=== madmom: creating DBNBeatTrackingProcessor ===", flush=True)
    beat_tracker = DBNBeatTrackingProcessor(fps=100)
    print(f"=== madmom: tracking beats ===", flush=True)
    beats = beat_tracker(beat_act)
    beats = list(beats.astype(float))
    print(f"=== madmom: beat tracking done, found {len(beats)} beats ===", flush=True)

    if len(beats) >= 2:
        intervals = np.diff(beats)
        avg_interval = np.median(intervals)
        tempo_bpm = 60.0 / avg_interval
    else:
        tempo_bpm = 120.0

    try:
        downbeat_proc = RNNDownBeatProcessor()
        downbeat_act = downbeat_proc(str(audio_path))

        downbeat_tracker = DBNDownBeatTrackingProcessor(beats_per_bar=[3, 4], fps=100)
        downbeat_result = downbeat_tracker(downbeat_act)

        downbeats = [float(db[0]) for db in downbeat_result if db[1] == 1]

        beat_counts = []
        for i in range(len(downbeats) - 1):
            count = sum(1 for b in beats if downbeats[i] <= b < downbeats[i + 1])
            beat_counts.append(count)

        if beat_counts:
            most_common = max(set(beat_counts), key=beat_counts.count)
            time_signature = f"{most_common}/4"
        else:
            time_signature = "4/4"

    except Exception as e:
        logger.warning(f"Downbeat detection failed: {e}, defaulting to 4/4")
        downbeats = [b for i, b in enumerate(beats) if i % 4 == 0]
        time_signature = "4/4"

    logger.info(f"Detected tempo: {tempo_bpm:.1f} BPM, time signature: {time_signature}")

    return BeatInfo(
        tempo_bpm=round(tempo_bpm, 1),
        time_signature=time_signature,
        beats=beats,
        downbeats=downbeats,
    )


async def detect_beats(audio_path: Path, timeout_seconds: float = 120.0) -> BeatInfo:
    """
    Detect tempo, beats, and downbeats using madmom.

    Args:
        audio_path: Path to input audio file
        timeout_seconds: Maximum time to wait for madmom before falling back to librosa

    Returns:
        BeatInfo with tempo, time signature, beat positions, and downbeat positions
    """
    logger.info(f"Detecting beats in {audio_path}")

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_run_madmom_sync, audio_path),
            timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        logger.warning(f"Madmom timed out after {timeout_seconds}s, using librosa fallback")
        return await _librosa_fallback(audio_path)
    except Exception as e:
        logger.error(f"Beat detection failed: {e}")
        return await _librosa_fallback(audio_path)


def _run_librosa_sync(audio_path: Path) -> BeatInfo:
    """Synchronous librosa beat detection (CPU-intensive)."""
    y, sr = librosa.load(str(audio_path))

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beats = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    if isinstance(tempo, np.ndarray):
        tempo = float(tempo[0])

    downbeats = [b for i, b in enumerate(beats) if i % 4 == 0]

    return BeatInfo(
        tempo_bpm=round(tempo, 1),
        time_signature="4/4",
        beats=beats,
        downbeats=downbeats,
    )


async def _librosa_fallback(audio_path: Path) -> BeatInfo:
    """Fallback beat detection using librosa."""
    try:
        return await asyncio.to_thread(_run_librosa_sync, audio_path)
    except Exception as e:
        logger.error(f"Librosa fallback also failed: {e}")
        return BeatInfo(
            tempo_bpm=120.0,
            time_signature="4/4",
            beats=[],
            downbeats=[],
        )
