"""REAPER connection wrapper using reapy library.

Based on patterns from https://github.com/wegitor/reaper-reapy-mcp
"""

import logging
import math
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)


class ReaperConnectionError(Exception):
    """Raised when REAPER connection fails."""

    pass


class ReaperAPI:
    """
    Wrapper for REAPER ReaScript API via reapy library.

    Provides connection management and error handling for REAPER operations.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        self.host = host or os.getenv("REAPER_HOST", "localhost")
        self.port = port or int(os.getenv("REAPER_PORT", "9000"))
        self._connected = False
        self._reapy = None
        self._RPR = None

    def connect(self) -> None:
        """Establish connection to REAPER."""
        try:
            import reapy
            from reapy import reascript_api as RPR

            self._reapy = reapy
            self._RPR = RPR

            reapy.connect()
            project = reapy.Project()
            _ = project.name
            self._connected = True
            logger.info(f"Connected to REAPER at {self.host}:{self.port}")
        except ImportError:
            raise ReaperConnectionError(
                "reapy library not installed. Install with: pip install reapy"
            )
        except Exception as e:
            self._connected = False
            raise ReaperConnectionError(
                f"Failed to connect to REAPER at {self.host}:{self.port}: {e}"
            )

    def disconnect(self) -> None:
        """Disconnect from REAPER."""
        self._connected = False
        logger.info("Disconnected from REAPER")

    @property
    def is_connected(self) -> bool:
        """Check if connected to REAPER."""
        return self._connected

    def ensure_connected(self) -> None:
        """Ensure connection is established, reconnect if needed."""
        if not self._connected:
            self.connect()

    @contextmanager
    def connection(self) -> Generator["ReaperAPI", None, None]:
        """Context manager for REAPER connection."""
        self.connect()
        try:
            yield self
        finally:
            self.disconnect()

    def get_project(self) -> Any:
        """Get the current REAPER project."""
        self.ensure_connected()
        return self._reapy.Project()

    def create_track(self, name: str, index: Optional[int] = None) -> Any:
        """Create a new track and return it."""
        self.ensure_connected()
        project = self.get_project()

        if index is None:
            index = len(project.tracks)

        project.add_track(index=index, name=name or "")
        track = project.tracks[index]
        logger.info(f"Created track '{name}' at index {index}")
        return track

    def add_fx_to_track(self, track_index: int, fx_name: str) -> bool:
        """
        Add an FX/VST plugin to a track.

        Args:
            track_index: 0-based track index
            fx_name: Plugin name (e.g., 'Vital', 'ReaSynth', 'ReaEQ')

        Returns:
            True if successful, False otherwise
        """
        self.ensure_connected()
        project = self.get_project()

        if track_index < 0 or track_index >= len(project.tracks):
            logger.error(f"Track index {track_index} out of range")
            return False

        track = project.tracks[track_index]

        # Build list of name variations to try (REAPER needs exact FX browser names)
        names_to_try = [
            fx_name,
            f"VST3i: {fx_name} ({fx_name} Audio)",  # VST3 instrument (e.g., Vital)
            f"VSTi: {fx_name} (x86_64) ({fx_name} Audio)",  # VST2 instrument
            f"VST3: {fx_name} ({fx_name} Audio)",  # VST3 effect
            f"VST: {fx_name} (x86_64) ({fx_name} Audio)",  # VST2 effect
            f"VST3i: {fx_name}",  # Short VST3 instrument
            f"VSTi: {fx_name}",  # Short VST2 instrument
            f"VST3: {fx_name}",  # Short VST3 effect
            f"VST: {fx_name}",  # Short VST2 effect
        ]

        for name in names_to_try:
            try:
                fx = track.add_fx(name)
                if fx:
                    logger.info(f"Added FX '{name}' to track {track_index}")
                    return True
            except Exception as e:
                logger.debug(f"Failed with name '{name}': {e}")

        logger.error(f"Failed to add FX '{fx_name}' to track {track_index}")
        return False

    def set_fx_param(
        self, track_index: int, fx_index: int, param_name: str, value: float
    ) -> bool:
        """Set an FX parameter by name."""
        self.ensure_connected()
        project = self.get_project()

        try:
            track = project.tracks[track_index]
            fx = track.fxs[fx_index]

            for param_idx in range(fx.n_params):
                if fx.params[param_idx].name.lower() == param_name.lower():
                    fx.params[param_idx].value = value
                    # Also try ReaScript API for reliability
                    try:
                        self._RPR.TrackFX_SetParamNormalized(
                            track.id, fx_index, param_idx, value
                        )
                    except Exception:
                        pass
                    logger.info(
                        f"Set param '{param_name}' to {value} on FX {fx_index}, track {track_index}"
                    )
                    return True

            logger.warning(f"Parameter '{param_name}' not found on FX {fx_index}")
            return False
        except Exception as e:
            logger.error(f"Failed to set FX param: {e}")
            return False

    def get_fx_list(self, track_index: int) -> list[dict[str, Any]]:
        """Get list of FX on a track."""
        self.ensure_connected()
        project = self.get_project()

        try:
            track = project.tracks[track_index]
            fx_list = []
            for i, fx in enumerate(track.fxs):
                fx_list.append(
                    {
                        "index": i,
                        "name": fx.name,
                        "enabled": getattr(fx, "enabled", True),
                    }
                )
            return fx_list
        except Exception as e:
            logger.error(f"Failed to get FX list: {e}")
            return []

    def create_midi_item(
        self, track_index: int, start_time: float, length: float = 4.0
    ) -> Optional[dict[str, Any]]:
        """
        Create an empty MIDI item on a track.

        Args:
            track_index: 0-based track index
            start_time: Start time in seconds
            length: Length of MIDI item in seconds

        Returns:
            Dict with 'item' (reapy Item), 'item_index', 'item_id' or None if failed
        """
        self.ensure_connected()
        project = self.get_project()

        if track_index < 0 or track_index >= len(project.tracks):
            logger.error(f"Track index {track_index} out of range")
            return None

        track = project.tracks[track_index]

        try:
            item = track.add_midi_item(start_time, start_time + length)
            if item is None:
                logger.error("track.add_midi_item returned None")
                return None

            # Ensure there's an active take
            take = item.active_take
            if take is None:
                take = item.add_take()
                if take is None:
                    logger.error("Failed to add take to MIDI item")
                    return None

            # Find the index of this item
            for i, track_item in enumerate(track.items):
                if track_item.id == item.id:
                    logger.info(
                        f"Created MIDI item on track {track_index} at {start_time}s, index {i}"
                    )
                    return {"item": item, "item_index": i, "item_id": str(item.id)}

            logger.warning(f"Created MIDI item but couldn't find index")
            return {"item": item, "item_index": -1, "item_id": str(item.id)}

        except Exception as e:
            logger.error(f"Failed to create MIDI item: {e}")
            return None

    def add_midi_note(
        self,
        track_index: int,
        item_index: int,
        pitch: int,
        start_time: float,
        length: float,
        velocity: int = 96,
        channel: int = 0,
    ) -> bool:
        """
        Add a MIDI note to a MIDI item.

        Args:
            track_index: 0-based track index
            item_index: Index of the MIDI item on the track
            pitch: MIDI note pitch (0-127)
            start_time: Start time in seconds (relative to item start)
            length: Note length in seconds
            velocity: Note velocity (0-127)
            channel: MIDI channel (0-15)

        Returns:
            True if successful
        """
        self.ensure_connected()
        project = self.get_project()

        try:
            track = project.tracks[track_index]
            item = track.items[item_index]
            take = item.active_take

            if take is None:
                logger.error("Item has no active take")
                return False

            note_end = start_time + length
            take.add_note(
                start=start_time,
                end=note_end,
                channel=channel,
                pitch=pitch,
                velocity=velocity,
            )
            logger.debug(f"Added note: pitch={pitch}, start={start_time}, vel={velocity}")
            return True

        except Exception as e:
            logger.error(f"Failed to add MIDI note: {e}")
            return False

    def add_midi_notes_bulk(
        self, track_index: int, item_index: int, notes: list[dict[str, Any]]
    ) -> int:
        """
        Add multiple MIDI notes to a MIDI item.

        Args:
            track_index: 0-based track index
            item_index: Index of the MIDI item on the track
            notes: List of note dicts with keys: pitch, start, length, velocity, channel

        Returns:
            Number of notes successfully added
        """
        self.ensure_connected()
        project = self.get_project()

        try:
            track = project.tracks[track_index]
            item = track.items[item_index]
            take = item.active_take

            if take is None:
                logger.error("Item has no active take")
                return 0

            added = 0
            for note in notes:
                try:
                    take.add_note(
                        start=note.get("start", 0),
                        end=note.get("start", 0) + note.get("length", 0.5),
                        channel=note.get("channel", 0),
                        pitch=note.get("pitch", 60),
                        velocity=note.get("velocity", 96),
                    )
                    added += 1
                except Exception as e:
                    logger.warning(f"Failed to add note {note}: {e}")

            logger.info(f"Added {added}/{len(notes)} MIDI notes")
            return added

        except Exception as e:
            logger.error(f"Failed to add MIDI notes: {e}")
            return 0

    def set_track_volume(self, track_index: int, volume_db: float) -> bool:
        """Set track volume in dB."""
        self.ensure_connected()
        project = self.get_project()

        try:
            track = project.tracks[track_index]
            # Convert dB to linear scale
            linear = 10 ** (volume_db / 20)
            self._RPR.SetMediaTrackInfo_Value(track.id, "D_VOL", linear)
            logger.info(f"Set track {track_index} volume to {volume_db}dB")
            return True
        except Exception as e:
            logger.error(f"Failed to set track volume: {e}")
            return False

    def set_track_pan(self, track_index: int, pan: float) -> bool:
        """Set track pan (-1.0 to 1.0)."""
        self.ensure_connected()
        project = self.get_project()

        try:
            track = project.tracks[track_index]
            track.pan = pan
            logger.info(f"Set track {track_index} pan to {pan}")
            return True
        except Exception as e:
            logger.error(f"Failed to set track pan: {e}")
            return False

    def set_track_mute(self, track_index: int, mute: bool) -> bool:
        """Set track mute state."""
        self.ensure_connected()
        project = self.get_project()

        try:
            track = project.tracks[track_index]
            track.mute = mute
            logger.info(f"Set track {track_index} mute to {mute}")
            return True
        except Exception as e:
            logger.error(f"Failed to set track mute: {e}")
            return False

    def get_track_state(self, track_index: int) -> Optional[dict[str, Any]]:
        """Get detailed state of a track."""
        self.ensure_connected()
        project = self.get_project()

        try:
            track = project.tracks[track_index]

            # Count MIDI items
            midi_item_count = 0
            has_midi = False
            for item in track.items:
                take = item.active_take
                if take and take.is_midi:
                    has_midi = True
                    midi_item_count += 1

            # Get first FX name as "instrument"
            instrument = ""
            if len(track.fxs) > 0:
                instrument = track.fxs[0].name

            # Convert volume from linear to dB
            volume_linear = self._RPR.GetMediaTrackInfo_Value(track.id, "D_VOL")
            volume_db = 20 * math.log10(volume_linear) if volume_linear > 0 else -60

            return {
                "name": track.name,
                "instrument": instrument,
                "volume_db": round(volume_db, 2),
                "pan": track.pan,
                "mute": track.mute,
                "has_midi": has_midi,
                "midi_item_count": midi_item_count,
                "fx_count": len(track.fxs),
            }
        except Exception as e:
            logger.error(f"Failed to get track state: {e}")
            return None

    def set_tempo(self, bpm: float) -> bool:
        """Set project tempo."""
        self.ensure_connected()
        project = self.get_project()

        try:
            project.bpm = float(bpm)
            logger.info(f"Set tempo to {bpm} BPM")
            return True
        except Exception as e:
            logger.error(f"Failed to set tempo: {e}")
            return False

    def set_time_signature(self, numerator: int, denominator: int) -> bool:
        """Set project time signature at position 0."""
        self.ensure_connected()
        project = self.get_project()

        try:
            # SetTempoTimeSigMarker(proj, ptidx, timepos, measurepos, beatpos, bpm, timesig_num, timesig_denom, lineartempo)
            # ptidx=-1 adds new marker, measurepos/beatpos=-1 to use timepos, bpm=-1 keeps current tempo
            self._RPR.SetTempoTimeSigMarker(project.id, -1, 0.0, -1, -1.0, -1, numerator, denominator, False)
            logger.info(f"Set time signature to {numerator}/{denominator}")
            return True
        except Exception as e:
            logger.error(f"Failed to set time signature: {e}")
            return False

    def render_project(
        self,
        output_path: str,
        start: float = 0,
        end: Optional[float] = None,
        samplerate: int = 44100,
        channels: int = 2,
    ) -> Optional[str]:
        """
        Render project to audio file.

        Args:
            output_path: Output file path
            start: Start time in seconds (optional)
            end: End time in seconds (optional, defaults to project length)
            samplerate: Sample rate (default 44100)
            channels: Number of channels (default 2)

        Returns:
            Output path if successful, None if failed
        """
        self.ensure_connected()
        project = self.get_project()
        RPR = self._RPR

        try:
            # Store current time selection
            old_start = project.time_selection.start
            old_end = project.time_selection.end

            try:
                # Prepare output path
                output_path = os.path.abspath(output_path)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                # Set time selection if provided
                if end is not None:
                    project.time_selection = (start, end)
                    RPR.GetSetProjectInfo(
                        project.id, "RENDER_BOUNDSFLAG", 2, True
                    )  # 2 = time selection
                else:
                    RPR.GetSetProjectInfo(
                        project.id, "RENDER_BOUNDSFLAG", 1, True
                    )  # 1 = entire project

                # Configure render settings
                RPR.GetSetProjectInfo(project.id, "RENDER_CHANNELS", channels, True)
                RPR.GetSetProjectInfo(project.id, "RENDER_SRATE", samplerate, True)

                # RENDER_FILE = directory, RENDER_PATTERN = filename (without extension)
                output_dir = os.path.dirname(output_path)
                output_filename = os.path.splitext(os.path.basename(output_path))[0]
                RPR.GetSetProjectInfo_String(project.id, "RENDER_FILE", output_dir, True)
                RPR.GetSetProjectInfo_String(project.id, "RENDER_PATTERN", output_filename, True)

                # Execute render (action 41824 = "File: Render project, using the most recent render settings")
                self._reapy.perform_action(41824)

                # Wait for render to complete
                time.sleep(0.5)

                if os.path.exists(output_path):
                    logger.info(f"Rendered project to {output_path}")
                    return output_path
                else:
                    logger.error(f"Render failed - output file not created at {output_path}")
                    return None

            finally:
                # Restore original time selection
                project.time_selection = (old_start, old_end)

        except Exception as e:
            logger.error(f"Failed to render project: {e}")
            return None

    def get_track_count(self) -> int:
        """Get number of tracks in project."""
        self.ensure_connected()
        return len(self.get_project().tracks)

    def clear_project(self) -> None:
        """Clear all tracks from current project."""
        self.ensure_connected()
        project = self.get_project()

        while len(project.tracks) > 0:
            project.tracks[0].delete()
        logger.info("Cleared all tracks from project")

    def insert_audio_file(
        self, track_index: int, file_path: str, start_time: float
    ) -> bool:
        """Insert an audio file on a track at specified time."""
        self.ensure_connected()
        project = self.get_project()
        RPR = self._RPR

        try:
            if not os.path.exists(file_path):
                logger.error(f"Audio file not found: {file_path}")
                return False

            track = project.tracks[track_index]

            # Select only this track
            RPR.SetOnlyTrackSelected(track.id)

            # Set cursor position
            project.cursor_position = start_time

            # Insert media
            RPR.InsertMedia(file_path, 0)

            logger.info(f"Inserted audio '{file_path}' on track {track_index} at {start_time}s")
            return True

        except Exception as e:
            logger.error(f"Failed to insert audio: {e}")
            return False


_reaper_api: Optional[ReaperAPI] = None


def get_reaper_api() -> ReaperAPI:
    """Get singleton REAPER API instance."""
    global _reaper_api
    if _reaper_api is None:
        _reaper_api = ReaperAPI()
    return _reaper_api
