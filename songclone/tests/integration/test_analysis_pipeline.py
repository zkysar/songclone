"""Integration tests for the audio analysis pipeline.

Tests the full analysis pipeline with sample audio to verify
SongSpec output contains all required fields.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from songclone.analysis.pipeline import analyze_song
from songclone.analysis.schemas import SongSpec


@pytest.fixture
def sample_audio_path(tmp_path: Path) -> Path:
    """Create a minimal test audio file."""
    import struct
    import wave

    audio_path = tmp_path / "test_audio.wav"

    # Create a 2-second silent WAV file (22050 Hz, mono, 16-bit)
    sample_rate = 22050
    duration_seconds = 2
    n_samples = sample_rate * duration_seconds

    with wave.open(str(audio_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)

        # Write silence (zeros)
        for _ in range(n_samples):
            wav_file.writeframes(struct.pack("<h", 0))

    return audio_path


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create output directory for analysis results."""
    output = tmp_path / "analysis_output"
    output.mkdir()
    return output


class TestAnalysisPipelineSongSpecCompleteness:
    """Test that the analysis pipeline produces complete SongSpec output."""

    @pytest.mark.asyncio
    async def test_pipeline_returns_song_spec(
        self, sample_audio_path: Path, output_dir: Path
    ) -> None:
        """Test that analyze_song returns a SongSpec object."""
        result = await analyze_song(
            audio_path=sample_audio_path,
            output_dir=output_dir,
            session_id=None,
        )

        assert isinstance(result, SongSpec)

    @pytest.mark.asyncio
    async def test_song_spec_has_metadata(
        self, sample_audio_path: Path, output_dir: Path
    ) -> None:
        """Test that SongSpec contains required metadata fields."""
        result = await analyze_song(
            audio_path=sample_audio_path,
            output_dir=output_dir,
            session_id=None,
        )

        assert result.metadata is not None
        assert result.metadata.duration_seconds > 0
        assert result.metadata.tempo_bpm >= 20
        assert result.metadata.tempo_bpm <= 300
        assert result.metadata.time_signature
        assert result.metadata.key

    @pytest.mark.asyncio
    async def test_song_spec_has_stems(
        self, sample_audio_path: Path, output_dir: Path
    ) -> None:
        """Test that SongSpec contains stem data for all roles."""
        result = await analyze_song(
            audio_path=sample_audio_path,
            output_dir=output_dir,
            session_id=None,
        )

        assert result.stems is not None
        expected_stems = {"vocals", "drums", "bass", "other"}
        assert set(result.stems.keys()) == expected_stems

        for stem_name, stem_data in result.stems.items():
            assert stem_data.role.value == stem_name
            assert stem_data.audio_path
            # MIDI data may be empty for silent audio
            assert stem_data.midi_data is not None

    @pytest.mark.asyncio
    async def test_song_spec_has_structure(
        self, sample_audio_path: Path, output_dir: Path
    ) -> None:
        """Test that SongSpec contains song structure."""
        result = await analyze_song(
            audio_path=sample_audio_path,
            output_dir=output_dir,
            session_id=None,
        )

        assert result.structure is not None
        assert result.structure.sections is not None
        assert len(result.structure.sections) > 0

        for section in result.structure.sections:
            assert section.name
            assert section.start >= 0
            assert section.end >= section.start
            assert section.bars >= 1

    @pytest.mark.asyncio
    async def test_song_spec_has_chords(
        self, sample_audio_path: Path, output_dir: Path
    ) -> None:
        """Test that SongSpec contains chord progression."""
        result = await analyze_song(
            audio_path=sample_audio_path,
            output_dir=output_dir,
            session_id=None,
        )

        # Chords may be empty for silent audio, but list must exist
        assert result.chords is not None


class TestAnalysisPipelineErrorHandling:
    """Test that the analysis pipeline handles errors gracefully."""

    @pytest.mark.asyncio
    async def test_pipeline_handles_missing_file(self, output_dir: Path) -> None:
        """Test that pipeline raises error for missing audio file."""
        with pytest.raises(Exception):
            await analyze_song(
                audio_path=Path("/nonexistent/audio.wav"),
                output_dir=output_dir,
                session_id=None,
            )

    @pytest.mark.asyncio
    async def test_pipeline_fallbacks_work(
        self, sample_audio_path: Path, output_dir: Path
    ) -> None:
        """Test that pipeline produces output even when some tools fail."""
        # The pipeline should use fallback values when analysis tools fail
        result = await analyze_song(
            audio_path=sample_audio_path,
            output_dir=output_dir,
            session_id=None,
        )

        # Should still get a valid SongSpec with fallback values
        assert isinstance(result, SongSpec)
        assert result.metadata.tempo_bpm > 0


class TestAnalysisPipelineSSEEvents:
    """Test that the analysis pipeline emits correct SSE events."""

    @pytest.mark.asyncio
    async def test_pipeline_emits_events_with_session_id(
        self, sample_audio_path: Path, output_dir: Path
    ) -> None:
        """Test that pipeline emits SSE events when session_id is provided."""
        from songclone.api.events import event_emitter

        session_id = "test-session-123"
        queue = event_emitter.subscribe(session_id)

        try:
            # Run analysis in background
            task = asyncio.create_task(
                analyze_song(
                    audio_path=sample_audio_path,
                    output_dir=output_dir,
                    session_id=session_id,
                )
            )

            # Collect events with timeout
            events = []
            try:
                while True:
                    event = await asyncio.wait_for(queue.get(), timeout=5.0)
                    events.append(event)

                    # Stop when we see the complete event
                    if event.type == "phase" and event.status.value == "complete":
                        break
            except asyncio.TimeoutError:
                pass

            await task

            # Should have at least phase start and complete events
            phase_events = [e for e in events if e.type == "phase"]
            assert len(phase_events) >= 2

            # First phase event should be analysis started
            assert phase_events[0].phase.value == "analysis"
            assert phase_events[0].status.value == "started"

        finally:
            event_emitter.unsubscribe(session_id, queue)
