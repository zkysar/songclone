"""Tests for MIDI editing tools."""

import base64
import pytest
from unittest.mock import MagicMock

from songclone.orchestrator.tools import (
    _midi_store,
    _song_spec_store,
    get_midi_summary,
    init_midi_store,
    quantize_midi,
    transpose_midi,
)


def _create_simple_midi() -> bytes:
    """Create a simple MIDI file with a few notes."""
    import mido

    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)

    track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(120)))

    # C4 (60) at time 0, length 0.5s
    track.append(mido.Message('note_on', note=60, velocity=100, time=0))
    track.append(mido.Message('note_off', note=60, velocity=0, time=240))  # 0.5s at 480 tpb

    # E4 (64) at time 0.5s, length 0.5s
    track.append(mido.Message('note_on', note=64, velocity=80, time=0))
    track.append(mido.Message('note_off', note=64, velocity=0, time=240))

    # G4 (67) at time 1.0s, length 0.5s
    track.append(mido.Message('note_on', note=67, velocity=90, time=0))
    track.append(mido.Message('note_off', note=67, velocity=0, time=240))

    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
        mid.save(f.name)
        with open(f.name, 'rb') as rf:
            return rf.read()


def _create_mock_song_spec(midi_b64: str):
    """Create a mock SongSpec with MIDI data."""
    mock_spec = MagicMock()
    mock_spec.metadata.tempo_bpm = 120
    mock_spec.metadata.key = "C major"
    mock_spec.metadata.time_signature = "4/4"
    mock_spec.metadata.duration_seconds = 10.0
    mock_spec.stems = {
        "bass": MagicMock(midi_data=midi_b64, role=MagicMock(value="bass")),
    }
    mock_spec.structure.sections = []
    return mock_spec


class TestMidiTools:
    """Test MIDI manipulation tools."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear stores before each test."""
        _midi_store.clear()
        _song_spec_store.clear()

    def test_init_midi_store(self):
        """Test MIDI store initialization."""
        midi_bytes = _create_simple_midi()
        midi_b64 = base64.b64encode(midi_bytes).decode()
        song_spec = _create_mock_song_spec(midi_b64)

        init_midi_store("test-session", song_spec)

        assert "test-session" in _midi_store
        assert "bass" in _midi_store["test-session"]
        assert _song_spec_store["test-session"] == song_spec

    def test_get_midi_summary(self):
        """Test MIDI summary returns correct statistics."""
        midi_bytes = _create_simple_midi()
        midi_b64 = base64.b64encode(midi_bytes).decode()
        song_spec = _create_mock_song_spec(midi_b64)
        init_midi_store("test-session", song_spec)

        result = get_midi_summary("test-session", "bass")

        assert result["status"] == "success"
        assert result["note_count"] == 3
        assert result["pitch_range"]["low"] == 60  # C4
        assert result["pitch_range"]["high"] == 67  # G4
        assert result["unique_pitches"] == 3

    def test_get_midi_summary_missing_stem(self):
        """Test MIDI summary handles missing stem."""
        midi_bytes = _create_simple_midi()
        midi_b64 = base64.b64encode(midi_bytes).decode()
        song_spec = _create_mock_song_spec(midi_b64)
        init_midi_store("test-session", song_spec)

        result = get_midi_summary("test-session", "vocals")

        assert result["status"] == "error"
        assert "not found" in result["error_message"]

    def test_transpose_midi_up(self):
        """Test transposing MIDI up by an octave."""
        midi_bytes = _create_simple_midi()
        midi_b64 = base64.b64encode(midi_bytes).decode()
        song_spec = _create_mock_song_spec(midi_b64)
        init_midi_store("test-session", song_spec)

        result = transpose_midi("test-session", "bass", 12)

        assert result["status"] == "success"
        assert result["notes_modified"] == 3
        assert result["pitch_range_before"]["low"] == 60  # C4
        assert result["pitch_range_after"]["low"] == 72  # C5 (up an octave)

    def test_transpose_midi_down(self):
        """Test transposing MIDI down."""
        midi_bytes = _create_simple_midi()
        midi_b64 = base64.b64encode(midi_bytes).decode()
        song_spec = _create_mock_song_spec(midi_b64)
        init_midi_store("test-session", song_spec)

        result = transpose_midi("test-session", "bass", -12)

        assert result["status"] == "success"
        assert result["pitch_range_after"]["low"] == 48  # Down an octave

    def test_transpose_midi_clamps_to_valid_range(self):
        """Test that transpose clamps notes to 0-127."""
        midi_bytes = _create_simple_midi()
        midi_b64 = base64.b64encode(midi_bytes).decode()
        song_spec = _create_mock_song_spec(midi_b64)
        init_midi_store("test-session", song_spec)

        # Transpose up by a lot - should clamp to 127
        result = transpose_midi("test-session", "bass", 100)

        assert result["status"] == "success"
        assert result["pitch_range_after"]["high"] <= 127

    def test_quantize_midi(self):
        """Test quantizing MIDI to a grid."""
        midi_bytes = _create_simple_midi()
        midi_b64 = base64.b64encode(midi_bytes).decode()
        song_spec = _create_mock_song_spec(midi_b64)
        init_midi_store("test-session", song_spec)

        result = quantize_midi("test-session", "bass", "1/8", 1.0)

        assert result["status"] == "success"
        assert result["notes_adjusted"] == 3
        assert result["grid_used"] == "1/8"
        assert result["strength_applied"] == 1.0

    def test_quantize_midi_partial_strength(self):
        """Test quantizing with partial strength."""
        midi_bytes = _create_simple_midi()
        midi_b64 = base64.b64encode(midi_bytes).decode()
        song_spec = _create_mock_song_spec(midi_b64)
        init_midi_store("test-session", song_spec)

        result = quantize_midi("test-session", "bass", "1/16", 0.5)

        assert result["status"] == "success"
        assert result["strength_applied"] == 0.5

    def test_midi_modifications_persist(self):
        """Test that modifications persist in the store for next execute_plan."""
        midi_bytes = _create_simple_midi()
        midi_b64 = base64.b64encode(midi_bytes).decode()
        song_spec = _create_mock_song_spec(midi_b64)
        init_midi_store("test-session", song_spec)

        # Get initial summary
        before = get_midi_summary("test-session", "bass")
        assert before["pitch_range"]["low"] == 60

        # Transpose up
        transpose_midi("test-session", "bass", 12)

        # Verify change persisted
        after = get_midi_summary("test-session", "bass")
        assert after["pitch_range"]["low"] == 72

    def test_session_not_found(self):
        """Test error handling for missing session."""
        result = transpose_midi("nonexistent-session", "bass", 12)
        assert result["status"] == "error"
        assert "not found" in result["error_message"]
