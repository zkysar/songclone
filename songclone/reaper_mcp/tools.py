"""REAPER MCP batch tool implementations.

Based on patterns from https://github.com/wegitor/reaper-reapy-mcp
"""

import base64
import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from songclone.reaper_mcp.reaper_api import (
    ReaperAPI,
    ReaperConnectionError,
    get_reaper_api,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models for Input/Output
# =============================================================================


class CreateProjectInput(BaseModel):
    tempo: float = Field(..., ge=20, le=300, description="Tempo in BPM")
    time_signature: str = Field(
        ..., pattern=r"^\d+/\d+$", description="Time signature, e.g., '4/4'"
    )
    duration_seconds: float = Field(..., ge=1, description="Project duration in seconds")


class CreateProjectOutput(BaseModel):
    success: bool
    project_path: str
    error: Optional[str] = None


class TrackConfig(BaseModel):
    name: str
    instrument_vst: str = Field(
        ..., description="VST plugin name, e.g., 'Vital', 'ReaSynth'"
    )
    instrument_preset: Optional[str] = None
    color: Optional[str] = None


class BatchCreateTracksInput(BaseModel):
    tracks: list[TrackConfig]


class FallbackInfo(BaseModel):
    requested: str
    used: str
    reason: str


class BatchCreateTracksOutput(BaseModel):
    success: bool
    track_ids: list[str]
    fallbacks: list[FallbackInfo] = Field(default_factory=list)
    error: Optional[str] = None


class MidiInsertItem(BaseModel):
    track_id: str
    midi_data: str = Field(..., description="Base64-encoded MIDI file")
    start_time: float = Field(0, description="Start time in seconds")
    velocity_scale: float = Field(1.0, ge=0, le=2, description="Velocity multiplier")


class BatchInsertMidiInput(BaseModel):
    items: list[MidiInsertItem]


class BatchInsertMidiOutput(BaseModel):
    success: bool
    items_inserted: int
    notes_inserted: int = 0
    error: Optional[str] = None


class FXItem(BaseModel):
    plugin: str = Field(..., description="Plugin name, e.g., 'ReaEQ', 'ReaComp'")
    preset: Optional[str] = None
    params: Optional[dict[str, Any]] = None


class FXConfig(BaseModel):
    track_id: str
    fx_chain: list[FXItem]


class BatchSetFXInput(BaseModel):
    fx_configs: list[FXConfig]


class BatchSetFXOutput(BaseModel):
    success: bool
    fx_added: int
    fx_failed: int = 0
    error: Optional[str] = None


class LevelConfig(BaseModel):
    track_id: str
    volume_db: Optional[float] = Field(None, ge=-60, le=12)
    pan: Optional[float] = Field(None, ge=-1, le=1)
    mute: Optional[bool] = None


class BatchSetLevelsInput(BaseModel):
    levels: list[LevelConfig]


class BatchSetLevelsOutput(BaseModel):
    success: bool
    tracks_updated: int
    error: Optional[str] = None


class RenderAudioInput(BaseModel):
    output_path: str
    format: str = Field("wav", description="Output format (WAV only per constitution)")
    start_time: Optional[float] = None
    end_time: Optional[float] = None


class RenderAudioOutput(BaseModel):
    success: bool
    path: str
    duration: float
    error: Optional[str] = None


class TrackState(BaseModel):
    id: str
    name: str
    instrument: str = ""
    volume_db: float = 0.0
    pan: float = 0.0
    mute: bool = False
    has_midi: bool = False
    midi_item_count: int = 0
    fx_count: int = 0


class GetProjectStateOutput(BaseModel):
    success: bool
    tracks: list[TrackState]
    error: Optional[str] = None


# =============================================================================
# Constants
# =============================================================================

FALLBACK_VST = "ReaSynth"
# Common VSTs that might be available - we'll try to add them and fall back if not
PREFERRED_VSTS = {"Vital", "Dexed", "ReaSynth", "ReaSamplOmatic5000", "Surge XT"}


# =============================================================================
# Helper Functions
# =============================================================================


def _parse_track_id(track_id: str) -> int:
    """Parse track_id string (e.g., 'track_0') to integer index."""
    if track_id.startswith("track_"):
        return int(track_id.split("_")[1])
    return int(track_id)


def _parse_midi_file(midi_bytes: bytes) -> list[dict[str, Any]]:
    """
    Parse MIDI file bytes into a list of note events.

    Returns list of dicts with keys: pitch, start, length, velocity, channel
    """
    try:
        import mido

        # Write to temp file and read with mido
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            f.write(midi_bytes)
            temp_path = Path(f.name)

        try:
            mid = mido.MidiFile(str(temp_path))
        finally:
            temp_path.unlink(missing_ok=True)

        notes = []
        ticks_per_beat = mid.ticks_per_beat
        tempo = 500000  # Default: 120 BPM

        for track in mid.tracks:
            current_time = 0  # in ticks
            active_notes: dict[tuple[int, int], dict] = {}  # (channel, pitch) -> note_on info

            for msg in track:
                current_time += msg.time

                # Update tempo if tempo message
                if msg.type == "set_tempo":
                    tempo = msg.tempo

                # Convert ticks to seconds
                time_seconds = mido.tick2second(current_time, ticks_per_beat, tempo)

                if msg.type == "note_on" and msg.velocity > 0:
                    active_notes[(msg.channel, msg.note)] = {
                        "pitch": msg.note,
                        "start": time_seconds,
                        "velocity": msg.velocity,
                        "channel": msg.channel,
                    }
                elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                    key = (msg.channel, msg.note)
                    if key in active_notes:
                        note = active_notes.pop(key)
                        note["length"] = time_seconds - note["start"]
                        if note["length"] > 0:
                            notes.append(note)

        logger.info(f"Parsed {len(notes)} notes from MIDI file")
        return notes

    except ImportError:
        logger.warning("mido library not available for MIDI parsing")
        return []
    except Exception as e:
        logger.error(f"Failed to parse MIDI file: {e}")
        return []


# =============================================================================
# Tool Implementations
# =============================================================================


async def create_project(input_data: CreateProjectInput) -> CreateProjectOutput:
    """Initialize a new REAPER project with tempo and time signature."""
    try:
        reaper = get_reaper_api()
        reaper.ensure_connected()
        reaper.clear_project()

        numerator, denominator = map(int, input_data.time_signature.split("/"))
        reaper.set_tempo(input_data.tempo)
        reaper.set_time_signature(numerator, denominator)

        logger.info(
            f"Created project: {input_data.tempo} BPM, {input_data.time_signature}"
        )

        return CreateProjectOutput(
            success=True,
            project_path="current_project",
        )
    except ReaperConnectionError as e:
        logger.error(f"Failed to create project: {e}")
        return CreateProjectOutput(
            success=False,
            project_path="",
            error=str(e),
        )


async def batch_create_tracks(
    input_data: BatchCreateTracksInput,
) -> BatchCreateTracksOutput:
    """Create multiple tracks with instruments in one call."""
    try:
        reaper = get_reaper_api()
        reaper.ensure_connected()

        track_ids: list[str] = []
        fallbacks: list[FallbackInfo] = []

        for i, track_config in enumerate(input_data.tracks):
            # Create the track
            track = reaper.create_track(track_config.name)
            track_id = f"track_{i}"
            track_ids.append(track_id)

            # Try to add the VST instrument
            vst_to_use = track_config.instrument_vst
            success = reaper.add_fx_to_track(i, track_config.instrument_vst)

            if not success:
                # Try fallback VST
                fallback_success = reaper.add_fx_to_track(i, FALLBACK_VST)
                if fallback_success:
                    fallbacks.append(
                        FallbackInfo(
                            requested=track_config.instrument_vst,
                            used=FALLBACK_VST,
                            reason=f"VST '{track_config.instrument_vst}' not available",
                        )
                    )
                    vst_to_use = FALLBACK_VST
                else:
                    logger.warning(
                        f"Could not add any VST to track {i}, track will be empty"
                    )
                    vst_to_use = "(none)"

            logger.info(f"Created track '{track_config.name}' with {vst_to_use}")

        return BatchCreateTracksOutput(
            success=True,
            track_ids=track_ids,
            fallbacks=fallbacks,
        )
    except ReaperConnectionError as e:
        logger.error(f"Failed to create tracks: {e}")
        return BatchCreateTracksOutput(
            success=False,
            track_ids=[],
            error=str(e),
        )


async def batch_insert_midi(input_data: BatchInsertMidiInput) -> BatchInsertMidiOutput:
    """Insert MIDI data into multiple tracks."""
    try:
        reaper = get_reaper_api()
        reaper.ensure_connected()

        items_inserted = 0
        total_notes_inserted = 0

        for item in input_data.items:
            try:
                track_index = _parse_track_id(item.track_id)

                # Decode and parse MIDI
                midi_bytes = base64.b64decode(item.midi_data)
                notes = _parse_midi_file(midi_bytes)

                if not notes:
                    logger.warning(f"No notes found in MIDI for {item.track_id}")
                    continue

                # Calculate MIDI duration for item length
                max_end = max(n["start"] + n["length"] for n in notes)
                item_length = max(max_end + 1.0, 4.0)  # At least 4 seconds

                # Create MIDI item on track
                midi_item = reaper.create_midi_item(
                    track_index=track_index,
                    start_time=item.start_time,
                    length=item_length,
                )

                if midi_item is None:
                    logger.error(f"Failed to create MIDI item on {item.track_id}")
                    continue

                item_index = midi_item["item_index"]

                # Apply velocity scaling and add notes
                scaled_notes = []
                for note in notes:
                    scaled_velocity = int(note["velocity"] * item.velocity_scale)
                    scaled_velocity = max(1, min(127, scaled_velocity))
                    scaled_notes.append(
                        {
                            "pitch": note["pitch"],
                            "start": note["start"],
                            "length": note["length"],
                            "velocity": scaled_velocity,
                            "channel": note["channel"],
                        }
                    )

                # Add notes to the MIDI item
                notes_added = reaper.add_midi_notes_bulk(
                    track_index=track_index,
                    item_index=item_index,
                    notes=scaled_notes,
                )

                total_notes_inserted += notes_added
                items_inserted += 1
                logger.info(
                    f"Inserted MIDI into {item.track_id} at {item.start_time}s "
                    f"({notes_added} notes)"
                )

            except Exception as e:
                logger.warning(f"Failed to insert MIDI for {item.track_id}: {e}")

        return BatchInsertMidiOutput(
            success=items_inserted > 0,
            items_inserted=items_inserted,
            notes_inserted=total_notes_inserted,
        )
    except ReaperConnectionError as e:
        logger.error(f"Failed to insert MIDI: {e}")
        return BatchInsertMidiOutput(
            success=False,
            items_inserted=0,
            error=str(e),
        )


async def batch_set_fx(input_data: BatchSetFXInput) -> BatchSetFXOutput:
    """Add/configure FX chains on multiple tracks."""
    try:
        reaper = get_reaper_api()
        reaper.ensure_connected()

        fx_added = 0
        fx_failed = 0

        for config in input_data.fx_configs:
            track_index = _parse_track_id(config.track_id)

            for fx in config.fx_chain:
                success = reaper.add_fx_to_track(track_index, fx.plugin)

                if success:
                    fx_added += 1
                    logger.info(f"Added {fx.plugin} to {config.track_id}")

                    # Set FX parameters if provided
                    if fx.params:
                        fx_list = reaper.get_fx_list(track_index)
                        if fx_list:
                            # Get index of the just-added FX (should be last)
                            fx_index = len(fx_list) - 1
                            for param_name, param_value in fx.params.items():
                                reaper.set_fx_param(
                                    track_index, fx_index, param_name, float(param_value)
                                )
                else:
                    fx_failed += 1
                    logger.warning(f"Failed to add {fx.plugin} to {config.track_id}")

        return BatchSetFXOutput(
            success=fx_added > 0 or fx_failed == 0,
            fx_added=fx_added,
            fx_failed=fx_failed,
        )
    except ReaperConnectionError as e:
        logger.error(f"Failed to set FX: {e}")
        return BatchSetFXOutput(
            success=False,
            fx_added=0,
            error=str(e),
        )


async def batch_set_levels(input_data: BatchSetLevelsInput) -> BatchSetLevelsOutput:
    """Set volume, pan, mute for multiple tracks."""
    try:
        reaper = get_reaper_api()
        reaper.ensure_connected()

        tracks_updated = 0

        for level in input_data.levels:
            track_index = _parse_track_id(level.track_id)
            updated = False

            if level.volume_db is not None:
                if reaper.set_track_volume(track_index, level.volume_db):
                    updated = True

            if level.pan is not None:
                if reaper.set_track_pan(track_index, level.pan):
                    updated = True

            if level.mute is not None:
                if reaper.set_track_mute(track_index, level.mute):
                    updated = True

            if updated:
                tracks_updated += 1
                logger.info(
                    f"Set levels for {level.track_id}: "
                    f"vol={level.volume_db}dB, pan={level.pan}, mute={level.mute}"
                )

        return BatchSetLevelsOutput(
            success=True,
            tracks_updated=tracks_updated,
        )
    except ReaperConnectionError as e:
        logger.error(f"Failed to set levels: {e}")
        return BatchSetLevelsOutput(
            success=False,
            tracks_updated=0,
            error=str(e),
        )


async def render_audio(input_data: RenderAudioInput) -> RenderAudioOutput:
    """Render project to audio file."""
    try:
        reaper = get_reaper_api()
        reaper.ensure_connected()

        start = input_data.start_time or 0
        end = input_data.end_time

        rendered_path = reaper.render_project(
            output_path=input_data.output_path,
            start=start,
            end=end,
        )

        if rendered_path is None:
            return RenderAudioOutput(
                success=False,
                path="",
                duration=0,
                error="Render failed - output file not created",
            )

        duration = (end - start) if end else 0

        logger.info(f"Rendered audio to {rendered_path}")

        return RenderAudioOutput(
            success=True,
            path=rendered_path,
            duration=duration,
        )
    except ReaperConnectionError as e:
        logger.error(f"Failed to render audio: {e}")
        return RenderAudioOutput(
            success=False,
            path="",
            duration=0,
            error=str(e),
        )


async def get_project_state() -> GetProjectStateOutput:
    """Get current state of all tracks for verification."""
    try:
        reaper = get_reaper_api()
        reaper.ensure_connected()

        track_count = reaper.get_track_count()
        tracks: list[TrackState] = []

        for i in range(track_count):
            state = reaper.get_track_state(i)
            if state:
                tracks.append(
                    TrackState(
                        id=f"track_{i}",
                        name=state["name"],
                        instrument=state["instrument"],
                        volume_db=state["volume_db"],
                        pan=state["pan"],
                        mute=state["mute"],
                        has_midi=state["has_midi"],
                        midi_item_count=state["midi_item_count"],
                        fx_count=state["fx_count"],
                    )
                )
            else:
                tracks.append(
                    TrackState(
                        id=f"track_{i}",
                        name=f"Track {i + 1}",
                    )
                )

        return GetProjectStateOutput(
            success=True,
            tracks=tracks,
        )
    except ReaperConnectionError as e:
        logger.error(f"Failed to get project state: {e}")
        return GetProjectStateOutput(
            success=False,
            tracks=[],
            error=str(e),
        )
