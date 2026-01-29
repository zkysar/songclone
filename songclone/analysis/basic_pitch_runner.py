"""MIDI extraction using Basic Pitch."""

import asyncio
import base64
import logging
import tempfile
from pathlib import Path

from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH

logger = logging.getLogger(__name__)


def _run_basic_pitch_sync(
    audio_path: Path,
    onset_threshold: float,
    frame_threshold: float,
    min_note_length: float,
) -> str:
    """Synchronous basic pitch MIDI extraction (CPU-intensive)."""
    model_output, midi_data, note_events = predict(
        str(audio_path),
        ICASSP_2022_MODEL_PATH,
        onset_threshold=onset_threshold,
        frame_threshold=frame_threshold,
        minimum_note_length=min_note_length,
    )

    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
        midi_data.write(f.name)
        midi_path = Path(f.name)

    with open(midi_path, "rb") as f:
        midi_bytes = f.read()

    midi_path.unlink()

    encoded = base64.b64encode(midi_bytes).decode("utf-8")
    logger.info(f"Extracted MIDI ({len(note_events)} notes) from {audio_path}")

    return encoded


async def extract_midi(
    audio_path: Path,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    min_note_length: float = 58,
) -> str:
    """
    Extract MIDI from audio using Basic Pitch.

    Args:
        audio_path: Path to input audio file
        onset_threshold: Onset detection threshold (0-1)
        frame_threshold: Frame detection threshold (0-1)
        min_note_length: Minimum note length in milliseconds

    Returns:
        Base64-encoded MIDI file data
    """
    logger.info(f"Extracting MIDI from {audio_path}")

    try:
        return await asyncio.to_thread(
            _run_basic_pitch_sync,
            audio_path,
            onset_threshold,
            frame_threshold,
            min_note_length,
        )
    except Exception as e:
        logger.error(f"MIDI extraction failed: {e}")
        return await _generate_empty_midi()


async def _generate_empty_midi() -> str:
    """Generate an empty MIDI file as fallback."""
    try:
        from midiutil import MIDIFile

        midi = MIDIFile(1)
        midi.addTempo(0, 0, 120)

        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            midi.writeFile(f)
            midi_path = Path(f.name)

        with open(midi_path, "rb") as f:
            midi_bytes = f.read()

        midi_path.unlink()

        return base64.b64encode(midi_bytes).decode("utf-8")

    except ImportError:
        header = bytes([
            0x4D, 0x54, 0x68, 0x64,
            0x00, 0x00, 0x00, 0x06,
            0x00, 0x00,
            0x00, 0x01,
            0x00, 0x60,
            0x4D, 0x54, 0x72, 0x6B,
            0x00, 0x00, 0x00, 0x04,
            0x00, 0xFF, 0x2F, 0x00,
        ])
        return base64.b64encode(header).decode("utf-8")
