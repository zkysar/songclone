"""Drum decomposition using librosa band-pass filters and onset detection."""

import base64
import logging
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def decompose_drums(audio_path: str, session_id: str | None = None) -> dict[str, Any]:
    """Decompose drum stem into kick/snare/hihat patterns.

    Uses band-pass filtering and onset detection to separate drum elements
    and analyze their patterns. Optionally creates separate MIDI tracks
    for each drum element.

    Args:
        audio_path: Path to the drum stem audio file (WAV).
        session_id: Optional session ID for storing separate MIDI tracks.

    Returns:
        dict with kick, snare, hihat patterns (hit_count, density_per_bar, pattern),
        overall_pattern, groove_feel, swing_amount, and midi_updated flag.
    """
    import librosa

    if not Path(audio_path).exists():
        return {"status": "error", "error_message": f"Audio file not found: {audio_path}"}

    try:
        y, sr = librosa.load(audio_path, sr=22050)

        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        duration = len(y) / sr
        num_bars = int(duration / (60 / tempo * 4)) if tempo > 0 else 1

        kick_y = _bandpass_filter(y, sr, 20, 150)
        snare_y = _bandpass_filter(y, sr, 150, 500)
        hihat_y = _bandpass_filter(y, sr, 5000, 15000)

        kick_onsets = librosa.onset.onset_detect(y=kick_y, sr=sr, units="time")
        snare_onsets = librosa.onset.onset_detect(y=snare_y, sr=sr, units="time")
        hihat_onsets = librosa.onset.onset_detect(y=hihat_y, sr=sr, units="time")

        kick_pattern = _analyze_pattern(kick_onsets, tempo, duration, "kick")
        snare_pattern = _analyze_pattern(snare_onsets, tempo, duration, "snare")
        hihat_pattern = _analyze_pattern(hihat_onsets, tempo, duration, "hihat")

        overall_pattern = _classify_overall_pattern(kick_pattern, snare_pattern)
        groove_feel, swing_amount = _analyze_groove(hihat_onsets, tempo)

        midi_updated = False
        if session_id:
            midi_updated = _create_separate_midi_tracks(
                session_id, kick_onsets, snare_onsets, hihat_onsets, tempo
            )

        return {
            "status": "success",
            "kick": {
                "hit_count": len(kick_onsets),
                "density_per_bar": round(len(kick_onsets) / max(num_bars, 1), 2),
                "pattern": kick_pattern["description"],
            },
            "snare": {
                "hit_count": len(snare_onsets),
                "density_per_bar": round(len(snare_onsets) / max(num_bars, 1), 2),
                "pattern": snare_pattern["description"],
            },
            "hihat": {
                "hit_count": len(hihat_onsets),
                "density_per_bar": round(len(hihat_onsets) / max(num_bars, 1), 2),
                "pattern": hihat_pattern["description"],
            },
            "overall_pattern": overall_pattern,
            "groove_feel": groove_feel,
            "swing_amount": round(swing_amount, 2),
            "tempo_bpm": round(tempo, 1),
            "num_bars": num_bars,
            "midi_updated": midi_updated,
        }

    except Exception as e:
        logger.error(f"Drum decomposition failed: {e}")
        return {"status": "error", "error_message": str(e)}


def _bandpass_filter(y: np.ndarray, sr: int, low: float, high: float) -> np.ndarray:
    """Apply band-pass filter using librosa."""
    import librosa
    from scipy.signal import butter, sosfilt

    nyquist = sr / 2
    low_norm = max(low / nyquist, 0.001)
    high_norm = min(high / nyquist, 0.999)

    if low_norm >= high_norm:
        return y

    try:
        sos = butter(4, [low_norm, high_norm], btype="band", output="sos")
        filtered = sosfilt(sos, y)
        return filtered
    except Exception:
        return y


def _analyze_pattern(
    onsets: np.ndarray,
    tempo: float,
    duration: float,
    drum_type: str,
) -> dict[str, Any]:
    """Analyze rhythm pattern from onset times."""
    if len(onsets) == 0:
        return {"description": "none", "density": 0, "regularity": 0}

    beat_duration = 60 / tempo
    bar_duration = beat_duration * 4

    beat_positions = []
    for onset in onsets:
        beat_in_bar = (onset % bar_duration) / beat_duration
        beat_positions.append(beat_in_bar)

    density = len(onsets) / (duration / bar_duration)

    if len(onsets) > 1:
        intervals = np.diff(onsets)
        regularity = 1 - (np.std(intervals) / (np.mean(intervals) + 1e-10))
        regularity = max(0, min(1, regularity))
    else:
        regularity = 1.0

    description = _classify_pattern(beat_positions, density, drum_type)

    return {
        "description": description,
        "density": round(density, 2),
        "regularity": round(regularity, 2),
    }


def _classify_pattern(
    beat_positions: list[float],
    density: float,
    drum_type: str,
) -> str:
    """Classify the pattern based on beat positions."""
    hist, _ = np.histogram(beat_positions, bins=8, range=(0, 4))

    if drum_type == "kick":
        if hist[0] > hist[2] and hist[0] > hist[4]:
            if density >= 3.5:
                return "four-on-floor"
            elif density >= 1.5:
                return "downbeat-heavy"
            else:
                return "sparse"
        elif hist[4] > hist[0]:
            return "offbeat"
        else:
            return "syncopated"

    elif drum_type == "snare":
        if hist[2] > 0 and hist[6] > 0:
            return "backbeat"
        elif hist[0] > hist[2]:
            return "downbeat"
        else:
            return "syncopated"

    elif drum_type == "hihat":
        if density >= 7:
            return "sixteenth-notes"
        elif density >= 3.5:
            return "eighth-notes"
        elif density >= 1.5:
            return "quarter-notes"
        else:
            return "sparse"

    return "irregular"


def _classify_overall_pattern(
    kick_pattern: dict[str, Any],
    snare_pattern: dict[str, Any],
) -> str:
    """Classify the overall drum pattern."""
    kick_desc = kick_pattern["description"]
    snare_desc = snare_pattern["description"]

    if kick_desc == "four-on-floor":
        return "4-on-floor"
    elif kick_desc == "downbeat-heavy" and snare_desc == "backbeat":
        return "rock/pop"
    elif kick_desc == "syncopated":
        return "syncopated/funk"
    elif kick_pattern["density"] < 1:
        return "sparse/minimal"
    else:
        return "mixed/complex"


def _analyze_groove(
    hihat_onsets: np.ndarray,
    tempo: float,
) -> tuple[str, float]:
    """Analyze groove feel and swing amount."""
    if len(hihat_onsets) < 4:
        return "unknown", 0.0

    beat_duration = 60 / tempo
    eighth_note = beat_duration / 2

    offbeat_deviations = []
    for onset in hihat_onsets:
        beat_pos = onset / eighth_note
        deviation = beat_pos - round(beat_pos)
        offbeat_deviations.append(deviation)

    avg_deviation = np.mean([abs(d) for d in offbeat_deviations])
    swing_bias = np.mean(offbeat_deviations)

    if abs(swing_bias) > 0.05:
        swing_amount = abs(swing_bias) * 100
        if swing_bias > 0:
            groove_feel = "swung"
        else:
            groove_feel = "pushed"
    elif avg_deviation < 0.02:
        groove_feel = "straight"
        swing_amount = 0.0
    else:
        groove_feel = "human"
        swing_amount = avg_deviation * 50

    return groove_feel, swing_amount


def _create_separate_midi_tracks(
    session_id: str,
    kick_onsets: np.ndarray,
    snare_onsets: np.ndarray,
    hihat_onsets: np.ndarray,
    tempo: float,
) -> bool:
    """Create separate MIDI tracks for kick, snare, hihat."""
    try:
        import mido

        from songclone.orchestrator.tools import _midi_store

        kick_midi = _onsets_to_midi(kick_onsets, pitch=36, tempo=tempo)
        snare_midi = _onsets_to_midi(snare_onsets, pitch=38, tempo=tempo)
        hihat_midi = _onsets_to_midi(hihat_onsets, pitch=42, tempo=tempo)

        if session_id in _midi_store:
            _midi_store[session_id]["drums_kick"] = kick_midi
            _midi_store[session_id]["drums_snare"] = snare_midi
            _midi_store[session_id]["drums_hihat"] = hihat_midi
            return True

        return False

    except Exception as e:
        logger.warning(f"Failed to create separate drum MIDI tracks: {e}")
        return False


def _onsets_to_midi(
    onsets: np.ndarray,
    pitch: int,
    tempo: float,
    velocity: int = 100,
) -> str:
    """Convert onset times to base64 MIDI."""
    import mido

    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)

    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo)))

    ticks_per_beat = mid.ticks_per_beat
    seconds_per_tick = 60.0 / tempo / ticks_per_beat
    note_length_ticks = int(0.1 / seconds_per_tick)

    events = []
    for onset in onsets:
        tick = int(onset / seconds_per_tick)
        events.append((tick, "on", pitch, velocity))
        events.append((tick + note_length_ticks, "off", pitch, 0))

    events.sort(key=lambda e: (e[0], 0 if e[1] == "on" else 1))

    current_tick = 0
    for tick, event_type, p, vel in events:
        delta = max(0, tick - current_tick)
        if event_type == "on":
            track.append(mido.Message("note_on", note=p, velocity=vel, time=delta))
        else:
            track.append(mido.Message("note_off", note=p, velocity=0, time=delta))
        current_tick = tick

    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
        temp_path = f.name
    try:
        mid.save(temp_path)
        with open(temp_path, "rb") as f:
            midi_bytes = f.read()
        return base64.b64encode(midi_bytes).decode()
    finally:
        Path(temp_path).unlink(missing_ok=True)
