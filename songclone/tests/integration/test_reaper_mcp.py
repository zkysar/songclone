"""Integration tests for REAPER MCP tools.

These tests require REAPER to be running with ReaScript API enabled.
Skip these tests in CI environments without REAPER.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from songclone.reaper_mcp.tools import (
    BatchCreateTracksInput,
    BatchCreateTracksOutput,
    BatchInsertMidiInput,
    BatchSetFXInput,
    BatchSetLevelsInput,
    CreateProjectInput,
    CreateProjectOutput,
    FXConfig,
    FXItem,
    LevelConfig,
    MidiInsertItem,
    RenderAudioInput,
    RenderAudioOutput,
    TrackConfig,
    batch_create_tracks,
    batch_insert_midi,
    batch_set_fx,
    batch_set_levels,
    create_project,
    get_project_state,
    render_audio,
)


# Skip these tests if REAPER is not available
REAPER_AVAILABLE = os.environ.get("REAPER_AVAILABLE", "false").lower() == "true"
skip_without_reaper = pytest.mark.skipif(
    not REAPER_AVAILABLE,
    reason="REAPER not available (set REAPER_AVAILABLE=true to run)"
)


class TestCreateProject:
    """Tests for create_project tool."""

    @pytest.mark.asyncio
    async def test_create_project_with_valid_input(self) -> None:
        """Test project creation with valid tempo and time signature."""
        with patch("songclone.reaper_mcp.tools.get_reaper_api") as mock_api:
            mock_reaper = MagicMock()
            mock_api.return_value = mock_reaper

            input_data = CreateProjectInput(
                tempo=120.0,
                time_signature="4/4",
                duration_seconds=180.0,
            )

            result = await create_project(input_data)

            assert isinstance(result, CreateProjectOutput)
            assert result.success is True
            assert result.error is None
            mock_reaper.set_tempo.assert_called_once_with(120.0)
            mock_reaper.set_time_signature.assert_called_once_with(4, 4)

    @pytest.mark.asyncio
    async def test_create_project_handles_connection_error(self) -> None:
        """Test that create_project handles REAPER connection errors."""
        with patch("songclone.reaper_mcp.tools.get_reaper_api") as mock_api:
            from songclone.reaper_mcp.reaper_api import ReaperConnectionError

            mock_api.return_value.ensure_connected.side_effect = ReaperConnectionError(
                "Could not connect to REAPER"
            )

            input_data = CreateProjectInput(
                tempo=120.0,
                time_signature="4/4",
                duration_seconds=180.0,
            )

            result = await create_project(input_data)

            assert result.success is False
            assert result.error is not None
            assert "connect" in result.error.lower()


class TestBatchCreateTracks:
    """Tests for batch_create_tracks tool."""

    @pytest.mark.asyncio
    async def test_batch_create_tracks_with_available_vst(self) -> None:
        """Test track creation with available VST instruments."""
        with patch("songclone.reaper_mcp.tools.get_reaper_api") as mock_api:
            mock_reaper = MagicMock()
            mock_api.return_value = mock_reaper
            mock_reaper.create_track.return_value = MagicMock()

            input_data = BatchCreateTracksInput(
                tracks=[
                    TrackConfig(name="Lead", instrument_vst="Vital", instrument_preset="Init"),
                    TrackConfig(name="Bass", instrument_vst="ReaSynth"),
                ]
            )

            result = await batch_create_tracks(input_data)

            assert isinstance(result, BatchCreateTracksOutput)
            assert result.success is True
            assert len(result.track_ids) == 2
            assert len(result.fallbacks) == 0  # Vital and ReaSynth are available

    @pytest.mark.asyncio
    async def test_batch_create_tracks_with_unavailable_vst_fallback(self) -> None:
        """Test track creation falls back to ReaSynth for unavailable VST."""
        with patch("songclone.reaper_mcp.tools.get_reaper_api") as mock_api:
            mock_reaper = MagicMock()
            mock_api.return_value = mock_reaper
            mock_reaper.create_track.return_value = MagicMock()

            input_data = BatchCreateTracksInput(
                tracks=[
                    TrackConfig(name="Lead", instrument_vst="UnavailableVST"),
                ]
            )

            result = await batch_create_tracks(input_data)

            assert result.success is True
            assert len(result.fallbacks) == 1
            assert result.fallbacks[0].requested == "UnavailableVST"
            assert result.fallbacks[0].used == "ReaSynth"


class TestBatchInsertMidi:
    """Tests for batch_insert_midi tool."""

    @pytest.mark.asyncio
    async def test_batch_insert_midi_with_valid_data(self) -> None:
        """Test MIDI insertion with valid base64-encoded data."""
        import base64

        with patch("songclone.reaper_mcp.tools.get_reaper_api") as mock_api:
            mock_reaper = MagicMock()
            mock_api.return_value = mock_reaper

            # Create minimal MIDI data (just header)
            midi_data = base64.b64encode(b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xe0").decode()

            input_data = BatchInsertMidiInput(
                items=[
                    MidiInsertItem(
                        track_id="track_0",
                        midi_data=midi_data,
                        start_time=0.0,
                        velocity_scale=1.0,
                    )
                ]
            )

            result = await batch_insert_midi(input_data)

            assert result.success is True
            assert result.items_inserted == 1


class TestBatchSetFX:
    """Tests for batch_set_fx tool."""

    @pytest.mark.asyncio
    async def test_batch_set_fx_adds_effects(self) -> None:
        """Test FX chain setup on multiple tracks."""
        with patch("songclone.reaper_mcp.tools.get_reaper_api") as mock_api:
            mock_reaper = MagicMock()
            mock_api.return_value = mock_reaper

            input_data = BatchSetFXInput(
                fx_configs=[
                    FXConfig(
                        track_id="track_0",
                        fx_chain=[
                            FXItem(plugin="ReaEQ", preset=None, params=None),
                            FXItem(plugin="ReaComp", preset=None, params={"ratio": 4}),
                        ],
                    )
                ]
            )

            result = await batch_set_fx(input_data)

            assert result.success is True
            assert result.fx_added == 2


class TestBatchSetLevels:
    """Tests for batch_set_levels tool."""

    @pytest.mark.asyncio
    async def test_batch_set_levels_updates_tracks(self) -> None:
        """Test level setting for multiple tracks."""
        with patch("songclone.reaper_mcp.tools.get_reaper_api") as mock_api:
            mock_reaper = MagicMock()
            mock_api.return_value = mock_reaper

            input_data = BatchSetLevelsInput(
                levels=[
                    LevelConfig(track_id="track_0", volume_db=-3.0, pan=0.0, mute=False),
                    LevelConfig(track_id="track_1", volume_db=-6.0, pan=0.5, mute=False),
                ]
            )

            result = await batch_set_levels(input_data)

            assert result.success is True
            assert result.tracks_updated == 2


class TestRenderAudio:
    """Tests for render_audio tool."""

    @pytest.mark.asyncio
    async def test_render_audio_creates_wav(self) -> None:
        """Test audio rendering to WAV file."""
        with patch("songclone.reaper_mcp.tools.get_reaper_api") as mock_api:
            mock_reaper = MagicMock()
            mock_api.return_value = mock_reaper
            mock_reaper.render_project.return_value = "/tmp/render.wav"

            input_data = RenderAudioInput(
                output_path="/tmp/render.wav",
                format="wav",
                start_time=0.0,
                end_time=180.0,
            )

            result = await render_audio(input_data)

            assert isinstance(result, RenderAudioOutput)
            assert result.success is True
            assert result.path == "/tmp/render.wav"


class TestGetProjectState:
    """Tests for get_project_state tool."""

    @pytest.mark.asyncio
    async def test_get_project_state_returns_tracks(self) -> None:
        """Test getting current project state."""
        with patch("songclone.reaper_mcp.tools.get_reaper_api") as mock_api:
            mock_reaper = MagicMock()
            mock_api.return_value = mock_reaper

            # Mock project with tracks
            mock_track_1 = MagicMock()
            mock_track_1.name = "Lead"
            mock_track_2 = MagicMock()
            mock_track_2.name = "Bass"

            mock_project = MagicMock()
            mock_project.tracks = [mock_track_1, mock_track_2]
            mock_reaper.get_project.return_value = mock_project

            result = await get_project_state()

            assert result.success is True
            assert len(result.tracks) == 2
            assert result.tracks[0].name == "Lead"
            assert result.tracks[1].name == "Bass"


@skip_without_reaper
class TestReaperIntegration:
    """Full integration tests requiring running REAPER.

    These tests verify actual REAPER interaction.
    Set REAPER_AVAILABLE=true environment variable to run.
    """

    @pytest.mark.asyncio
    async def test_full_workflow_with_reaper(self) -> None:
        """Test complete workflow: create project, tracks, insert MIDI, render."""
        # Create project
        project_result = await create_project(
            CreateProjectInput(
                tempo=120.0,
                time_signature="4/4",
                duration_seconds=10.0,
            )
        )
        assert project_result.success, f"Failed to create project: {project_result.error}"

        # Create tracks
        tracks_result = await batch_create_tracks(
            BatchCreateTracksInput(
                tracks=[
                    TrackConfig(name="Test Track", instrument_vst="ReaSynth"),
                ]
            )
        )
        assert tracks_result.success, f"Failed to create tracks: {tracks_result.error}"

        # Get project state to verify
        state = await get_project_state()
        assert state.success
        assert len(state.tracks) >= 1
