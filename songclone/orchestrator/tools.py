"""ADK tool functions for the orchestrator agents."""

import base64
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from songclone.analysis.schemas import SongSpec
from songclone.orchestrator.schemas import (
    EvaluationMethod,
    EvaluationResult,
    ExecutionPlan,
    FeedbackCategory,
    FeedbackItem,
    FXConfig,
    InstrumentConfig,
    MixSettings,
    Scores,
    TrackPlan,
    TrackRole,
)

logger = logging.getLogger(__name__)

# In-memory MIDI store (per session) - avoids passing Base64 MIDI through LLM context
# Structure: session_id -> {stem_name -> base64_midi}
_midi_store: dict[str, dict[str, str]] = {}

# Store song_spec per session for execute_plan to access
_song_spec_store: dict[str, SongSpec] = {}

# Store the latest plan per session - avoids LLM needing to pass JSON between tools
# Structure: session_id -> ExecutionPlan
_plan_store: dict[str, ExecutionPlan] = {}

# Analysis cache (per session) - stores results from agentic analysis tools
# Structure: session_id -> {analysis_type -> result_dict}
_analysis_cache: dict[str, dict[str, Any]] = {}


def get_cached_analysis(session_id: str, analysis_type: str) -> dict | None:
    """Get cached analysis result.

    Args:
        session_id: Current session ID.
        analysis_type: Type of analysis (genre, spectral, instrument, drums, effects, vst).

    Returns:
        Cached analysis result dict, or None if not cached.
    """
    if session_id in _analysis_cache:
        return _analysis_cache[session_id].get(analysis_type)
    return None


def cache_analysis(session_id: str, analysis_type: str, result: dict) -> None:
    """Cache analysis result for use in planning.

    Args:
        session_id: Current session ID.
        analysis_type: Type of analysis (genre, spectral, instrument, drums, effects, vst).
        result: Analysis result dict to cache.
    """
    if session_id not in _analysis_cache:
        _analysis_cache[session_id] = {}
    _analysis_cache[session_id][analysis_type] = result
    logger.info(f"Cached {analysis_type} analysis for session {session_id}")

PLANNING_PROMPT_PATH = Path(__file__).parent / "prompts" / "planning.txt"
EVALUATION_PROMPT_PATH = Path(__file__).parent / "prompts" / "evaluation.txt"


def init_midi_store(session_id: str, song_spec: SongSpec) -> None:
    """Initialize MIDI store from song_spec stems.

    Call this before running the orchestrator to populate the MIDI store
    with the initial MIDI data from analysis.

    Args:
        session_id: Current session ID.
        song_spec: Song specification containing stems with MIDI data.
    """
    _midi_store[session_id] = {}
    for stem_name, stem in song_spec.stems.items():
        if stem.midi_data:
            _midi_store[session_id][stem_name] = stem.midi_data
    _song_spec_store[session_id] = song_spec
    logger.info(f"MIDI store initialized for session {session_id}: {list(_midi_store[session_id].keys())}")


def get_midi_from_store(session_id: str, stem_name: str) -> str | None:
    """Get MIDI data from store, falling back to song_spec if not in store."""
    if session_id in _midi_store and stem_name in _midi_store[session_id]:
        return _midi_store[session_id][stem_name]
    if session_id in _song_spec_store:
        stem = _song_spec_store[session_id].stems.get(stem_name)
        if stem:
            return stem.midi_data
    return None


def _parse_midi_to_notes(midi_b64: str) -> list[dict[str, Any]]:
    """Parse base64 MIDI to note dicts."""
    from songclone.reaper_mcp.tools import _parse_midi_file
    midi_bytes = base64.b64decode(midi_b64)
    return _parse_midi_file(midi_bytes)


def _notes_to_midi(notes: list[dict[str, Any]], tempo_bpm: float = 120) -> bytes:
    """Convert note dicts back to MIDI file bytes."""
    import mido

    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)

    track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(tempo_bpm)))

    if not notes:
        return _midi_to_bytes(mid)

    # Sort by start time, create note_on/note_off pairs
    events = []
    for n in notes:
        events.append((n["start"], "on", n["pitch"], n["velocity"], n.get("channel", 0)))
        events.append((n["start"] + n["length"], "off", n["pitch"], 0, n.get("channel", 0)))
    events.sort(key=lambda e: (e[0], 0 if e[1] == "on" else 1))

    ticks_per_beat = mid.ticks_per_beat
    seconds_per_tick = 60.0 / tempo_bpm / ticks_per_beat
    current_tick = 0

    for time_sec, event_type, pitch, vel, ch in events:
        target_tick = int(time_sec / seconds_per_tick)
        delta = max(0, target_tick - current_tick)
        if event_type == "on":
            track.append(mido.Message('note_on', note=pitch, velocity=vel, channel=ch, time=delta))
        else:
            track.append(mido.Message('note_off', note=pitch, velocity=0, channel=ch, time=delta))
        current_tick = target_tick

    return _midi_to_bytes(mid)


def _midi_to_bytes(mid) -> bytes:
    """Convert mido MidiFile to bytes."""
    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
        temp_path = f.name
    try:
        mid.save(temp_path)
        with open(temp_path, 'rb') as mf:
            return mf.read()
    finally:
        Path(temp_path).unlink(missing_ok=True)


def transpose_midi(session_id: str, stem_name: str, semitones: int) -> dict[str, Any]:
    """Transpose all notes in a stem's MIDI by semitones.

    Use this tool to fix pitch problems identified during evaluation.
    The modified MIDI will be used in the next execute_plan call.

    Args:
        session_id: Current session ID.
        stem_name: Stem to transpose (vocals, drums, bass, other).
        semitones: Semitones to shift (-24 to +24). Positive = higher pitch.

    Returns:
        dict with status, notes_modified, pitch_range_before, pitch_range_after.
    """
    print(f"=== TRANSPOSE_MIDI CALLED: session={session_id}, stem={stem_name}, semitones={semitones} ===", flush=True)

    if session_id not in _midi_store:
        return {"status": "error", "error_message": f"Session {session_id} not found in MIDI store"}

    midi_b64 = get_midi_from_store(session_id, stem_name)
    if not midi_b64:
        return {"status": "error", "error_message": f"Stem '{stem_name}' not found in session"}

    semitones = max(-24, min(24, semitones))

    try:
        notes = _parse_midi_to_notes(midi_b64)
        if not notes:
            return {"status": "error", "error_message": "No notes found in MIDI"}

        pitches_before = [n["pitch"] for n in notes]
        min_before, max_before = min(pitches_before), max(pitches_before)

        for note in notes:
            note["pitch"] = max(0, min(127, note["pitch"] + semitones))

        pitches_after = [n["pitch"] for n in notes]
        min_after, max_after = min(pitches_after), max(pitches_after)

        tempo = 120
        if session_id in _song_spec_store:
            tempo = _song_spec_store[session_id].metadata.tempo_bpm

        new_midi = _notes_to_midi(notes, tempo)
        _midi_store[session_id][stem_name] = base64.b64encode(new_midi).decode()

        print(f"=== TRANSPOSE_MIDI SUCCESS: {len(notes)} notes transposed ===", flush=True)
        return {
            "status": "success",
            "notes_modified": len(notes),
            "pitch_range_before": {"low": min_before, "high": max_before},
            "pitch_range_after": {"low": min_after, "high": max_after},
        }

    except Exception as e:
        logger.error(f"Transpose failed: {e}")
        return {"status": "error", "error_message": str(e)}


def quantize_midi(
    session_id: str,
    stem_name: str,
    grid: str = "1/16",
    strength: float = 1.0,
) -> dict[str, Any]:
    """Quantize note timing to a rhythmic grid.

    Use this tool to fix timing issues identified during evaluation.
    The modified MIDI will be used in the next execute_plan call.

    Args:
        session_id: Current session ID.
        stem_name: Stem to quantize (vocals, drums, bass, other).
        grid: Rhythmic grid ("1/4", "1/8", "1/16", "1/32").
        strength: 0.0 (no change) to 1.0 (hard snap).

    Returns:
        dict with status, notes_adjusted, avg_shift_ms.
    """
    print(f"=== QUANTIZE_MIDI CALLED: session={session_id}, stem={stem_name}, grid={grid}, strength={strength} ===", flush=True)

    if session_id not in _midi_store:
        return {"status": "error", "error_message": f"Session {session_id} not found in MIDI store"}

    midi_b64 = get_midi_from_store(session_id, stem_name)
    if not midi_b64:
        return {"status": "error", "error_message": f"Stem '{stem_name}' not found in session"}

    # Grid values in beats (quarter notes)
    grid_values = {"1/4": 1.0, "1/8": 0.5, "1/16": 0.25, "1/32": 0.125}
    grid_beats = grid_values.get(grid, 0.25)

    strength = max(0.0, min(1.0, strength))

    try:
        notes = _parse_midi_to_notes(midi_b64)
        if not notes:
            return {"status": "error", "error_message": "No notes found in MIDI"}

        tempo = 120
        if session_id in _song_spec_store:
            tempo = _song_spec_store[session_id].metadata.tempo_bpm

        # Convert grid to seconds
        seconds_per_beat = 60.0 / tempo
        grid_seconds = grid_beats * seconds_per_beat

        total_shift = 0.0
        for note in notes:
            nearest = round(note["start"] / grid_seconds) * grid_seconds
            shift = nearest - note["start"]
            note["start"] += shift * strength
            total_shift += abs(shift * strength)

        avg_shift_ms = (total_shift / len(notes)) * 1000 if notes else 0

        new_midi = _notes_to_midi(notes, tempo)
        _midi_store[session_id][stem_name] = base64.b64encode(new_midi).decode()

        print(f"=== QUANTIZE_MIDI SUCCESS: {len(notes)} notes quantized, avg shift {avg_shift_ms:.1f}ms ===", flush=True)
        return {
            "status": "success",
            "notes_adjusted": len(notes),
            "avg_shift_ms": round(avg_shift_ms, 2),
            "grid_used": grid,
            "strength_applied": strength,
        }

    except Exception as e:
        logger.error(f"Quantize failed: {e}")
        return {"status": "error", "error_message": str(e)}


def get_midi_summary(session_id: str, stem_name: str) -> dict[str, Any]:
    """Get MIDI analysis without returning raw data.

    Use this tool to understand the MIDI content before making modifications.
    This is token-efficient as it returns statistics, not raw MIDI bytes.

    Args:
        session_id: Current session ID.
        stem_name: Stem to analyze (vocals, drums, bass, other).

    Returns:
        dict with note_count, pitch_range, velocity_stats, duration_seconds,
        notes_per_second, unique_pitches.
    """
    print(f"=== GET_MIDI_SUMMARY CALLED: session={session_id}, stem={stem_name} ===", flush=True)

    midi_b64 = get_midi_from_store(session_id, stem_name)
    if not midi_b64:
        return {"status": "error", "error_message": f"Stem '{stem_name}' not found in session {session_id}"}

    try:
        notes = _parse_midi_to_notes(midi_b64)
        if not notes:
            return {
                "status": "success",
                "note_count": 0,
                "pitch_range": None,
                "velocity_stats": None,
                "duration_seconds": 0,
                "notes_per_second": 0,
                "unique_pitches": 0,
            }

        pitches = [n["pitch"] for n in notes]
        velocities = [n["velocity"] for n in notes]
        duration = max(n["start"] + n["length"] for n in notes)

        print(f"=== GET_MIDI_SUMMARY SUCCESS: {len(notes)} notes, {duration:.1f}s ===", flush=True)
        return {
            "status": "success",
            "note_count": len(notes),
            "pitch_range": {"low": min(pitches), "high": max(pitches)},
            "velocity_stats": {
                "min": min(velocities),
                "max": max(velocities),
                "avg": round(sum(velocities) / len(velocities), 1),
            },
            "duration_seconds": round(duration, 2),
            "notes_per_second": round(len(notes) / duration, 2) if duration > 0 else 0,
            "unique_pitches": len(set(pitches)),
        }

    except Exception as e:
        logger.error(f"MIDI summary failed: {e}")
        return {"status": "error", "error_message": str(e)}


def generate_plan(
    session_id: str,
    previous_feedback: str | None = None,
    iteration: int = 1,
) -> dict[str, Any]:
    """Generate an execution plan for recreating a song in REAPER.

    Use this tool to create a detailed plan for how to set up tracks,
    instruments, and effects to recreate the analyzed song.

    IMPORTANT: The song analysis is automatically retrieved from the session.
    You do NOT need to pass the song_spec_json - just pass the session_id.

    Args:
        session_id: Session ID to retrieve song analysis from.
        previous_feedback: Optional JSON string with feedback from previous iteration evaluation.
        iteration: Current iteration number (1 = first attempt).

    Returns:
        dict: Contains 'status' ('success' or 'error') and either 'plan' with
              the ExecutionPlan JSON or 'error_message' with details.
    """
    print(f"=== GENERATE_PLAN CALLED: session_id={session_id}, iteration={iteration} ===", flush=True)

    # Retrieve song_spec from session store - LLM doesn't need to pass it
    if session_id not in _song_spec_store:
        print(f"=== GENERATE_PLAN ERROR: Session {session_id} not found ===", flush=True)
        return {"status": "error", "error_message": f"Session {session_id} not found. Initialize with init_midi_store first."}

    song_spec = _song_spec_store[session_id]
    print(f"=== Song spec retrieved: {song_spec.metadata.tempo_bpm} BPM ===", flush=True)

    user_message = _build_planning_message(song_spec, previous_feedback, iteration, session_id)
    print(f"=== Planning message length: {len(user_message)} chars ===", flush=True)

    try:
        from google import genai

        print(f"=== Calling Gemini API for planning... ===", flush=True)
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

        with open(PLANNING_PROMPT_PATH) as f:
            system_prompt = f.read()

        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=user_message,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
            },
        )
        print(f"=== Gemini planning response received ===", flush=True)

        plan_data = json.loads(response.text)
        plan = ExecutionPlan.model_validate(plan_data)
        print(f"=== Plan validated: {len(plan.tracks)} tracks, reasoning: {plan.reasoning[:100]}... ===", flush=True)

        # Store the plan in session so execute_plan can retrieve it
        _plan_store[session_id] = plan
        print(f"=== Plan stored in session {session_id} ===", flush=True)

        return {
            "status": "success",
            "plan_stored": True,
            "track_count": len(plan.tracks),
            "reasoning": plan.reasoning,
            "tracks": [{"name": t.name, "role": t.role.value, "vst": t.instrument.vst} for t in plan.tracks],
        }

    except Exception as e:
        logger.warning(f"AI planning failed: {e}, using fallback")
        plan = _generate_fallback_plan(song_spec)

        # Store fallback plan in session too
        _plan_store[session_id] = plan
        print(f"=== Fallback plan stored in session {session_id} ===", flush=True)

        return {
            "status": "success",
            "plan_stored": True,
            "track_count": len(plan.tracks),
            "reasoning": plan.reasoning,
            "tracks": [{"name": t.name, "role": t.role.value, "vst": t.instrument.vst} for t in plan.tracks],
            "fallback": True,
        }


def _repair_json(json_str: str) -> str:
    """Attempt to repair common JSON errors from LLM output."""
    import re

    repaired = json_str.strip()

    # Remove markdown code blocks if present
    if repaired.startswith("```"):
        lines = repaired.split("\n")
        # Find start and end of code block
        start_idx = 1 if lines[0].startswith("```") else 0
        end_idx = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == "```":
                end_idx = i
                break
        repaired = "\n".join(lines[start_idx:end_idx])

    # Replace single quotes with double quotes (common LLM error)
    # But be careful not to replace quotes inside strings
    # Simple approach: replace 'key': with "key":
    repaired = re.sub(r"'([^']+)'(\s*:)", r'"\1"\2', repaired)

    # Fix trailing commas before closing braces/brackets
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)

    # Fix missing quotes around property names
    repaired = re.sub(r"(\{|\,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', repaired)

    return repaired


def execute_plan(
    session_id: str,
    output_path: str,
) -> dict[str, Any]:
    """Execute a recreation plan in REAPER DAW.

    Use this tool after generating a plan to actually create the tracks,
    load instruments, insert MIDI, and render the audio.

    IMPORTANT: The plan is automatically retrieved from the session (set by generate_plan).
    You do NOT need to pass the plan JSON - just call execute_plan after generate_plan.

    Args:
        session_id: Session ID to retrieve the plan and MIDI data from.
        output_path: File path where the rendered audio should be saved.

    Returns:
        dict: Contains 'status' ('success' or 'error') and either
              'rendered_path' or 'error_message'.
    """
    print(f"=== EXECUTE_PLAN CALLED ===", flush=True)
    print(f"=== session_id: {session_id}, output_path: {output_path} ===", flush=True)

    if session_id not in _song_spec_store:
        return {"status": "error", "error_message": f"Session {session_id} not found. MIDI store not initialized."}

    if session_id not in _plan_store:
        return {"status": "error", "error_message": f"No plan found for session {session_id}. Call generate_plan first."}

    song_spec = _song_spec_store[session_id]
    plan = _plan_store[session_id]
    print(f"=== Retrieved plan from session: {len(plan.tracks)} tracks ===", flush=True)

    try:
        return _execute_plan_sync(plan, song_spec, output_path, session_id)
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error_message": str(e)}


def _execute_plan_sync(
    plan: ExecutionPlan,
    song_spec: SongSpec,
    output_path: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Synchronous implementation of plan execution."""
    from songclone.reaper_mcp.reaper_api import get_reaper_api, ReaperConnectionError
    from songclone.reaper_mcp.tools import _parse_midi_file

    try:
        reaper = get_reaper_api()
        reaper.ensure_connected()
        print(f"=== Connected to REAPER ===", flush=True)
    except ReaperConnectionError as e:
        print(f"=== REAPER connection failed: {e} ===", flush=True)
        return {"status": "error", "error_message": f"REAPER connection failed: {e}"}

    # Clear and set up project
    print(f"=== Clearing project ===", flush=True)
    reaper.clear_project()

    print(f"=== Setting tempo to {song_spec.metadata.tempo_bpm} BPM ===", flush=True)
    reaper.set_tempo(song_spec.metadata.tempo_bpm)

    numerator, denominator = map(int, song_spec.metadata.time_signature.split("/"))
    reaper.set_time_signature(numerator, denominator)

    # Create tracks
    track_ids: list[str] = []
    print(f"=== Creating {len(plan.tracks)} tracks ===", flush=True)
    for i, track in enumerate(plan.tracks):
        print(f"=== Creating track {i}: {track.name} with {track.instrument.vst} ===", flush=True)
        reaper.create_track(track.name)
        track_id = f"track_{i}"
        track_ids.append(track_id)

        # Add instrument VST
        success = reaper.add_fx_to_track(i, track.instrument.vst)
        if not success:
            print(f"=== VST {track.instrument.vst} failed, trying ReaSynth ===", flush=True)
            reaper.add_fx_to_track(i, "ReaSynth")

    # Insert MIDI
    print(f"=== Inserting MIDI ===", flush=True)
    total_notes = 0
    for i, track in enumerate(plan.tracks):
        stem_name = track.midi_source
        print(f"=== Track {i} ({track.name}): looking for stem '{stem_name}' ===", flush=True)

        # Read MIDI from store (may have been modified by tools) or fallback to song_spec
        midi_data = None
        if session_id:
            midi_data = get_midi_from_store(session_id, stem_name)
            if midi_data:
                print(f"=== Using MIDI from store for '{stem_name}' ===", flush=True)

        if not midi_data:
            if stem_name not in song_spec.stems:
                print(f"=== Stem '{stem_name}' not found in song_spec ===", flush=True)
                continue
            stem = song_spec.stems[stem_name]
            if not stem.midi_data:
                print(f"=== Stem '{stem_name}' has no MIDI data ===", flush=True)
                continue
            midi_data = stem.midi_data

        print(f"=== Stem '{stem_name}' has {len(midi_data)} bytes of MIDI ===", flush=True)

        try:
            midi_bytes = base64.b64decode(midi_data)
            notes = _parse_midi_file(midi_bytes)
            print(f"=== Parsed {len(notes)} notes from MIDI ===", flush=True)

            if not notes:
                print(f"=== No notes parsed from MIDI ===", flush=True)
                continue

            # Calculate MIDI duration
            max_end = max(n["start"] + n["length"] for n in notes)
            item_length = max(max_end + 1.0, 4.0)

            # Create MIDI item
            midi_item = reaper.create_midi_item(
                track_index=i,
                start_time=0,
                length=item_length,
            )

            if midi_item is None:
                print(f"=== Failed to create MIDI item on track {i} ===", flush=True)
                continue

            item_index = midi_item["item_index"]

            # Apply velocity scaling
            velocity_scale = 1.0
            if track.midi_transform:
                velocity_scale = track.midi_transform.velocity_scale

            scaled_notes = []
            for note in notes:
                scaled_velocity = int(note["velocity"] * velocity_scale)
                scaled_velocity = max(1, min(127, scaled_velocity))
                scaled_notes.append({
                    "pitch": note["pitch"],
                    "start": note["start"],
                    "length": note["length"],
                    "velocity": scaled_velocity,
                    "channel": note["channel"],
                })

            # Add notes
            notes_added = reaper.add_midi_notes_bulk(
                track_index=i,
                item_index=item_index,
                notes=scaled_notes,
            )
            total_notes += notes_added
            print(f"=== Added {notes_added} notes to track {i} ===", flush=True)

        except Exception as e:
            print(f"=== Error inserting MIDI for track {i}: {e} ===", flush=True)
            import traceback
            traceback.print_exc()

    print(f"=== Total notes inserted: {total_notes} ===", flush=True)

    # Set FX
    print(f"=== Setting FX ===", flush=True)
    for i, track in enumerate(plan.tracks):
        if track.fx:
            for fx in track.fx:
                success = reaper.add_fx_to_track(i, fx.plugin)
                print(f"=== Added FX {fx.plugin} to track {i}: {success} ===", flush=True)

    # Set levels
    print(f"=== Setting levels ===", flush=True)
    for i, track in enumerate(plan.tracks):
        reaper.set_track_volume(i, track.mix.volume_db)
        reaper.set_track_pan(i, track.mix.pan)
        if track.mix.mute:
            reaper.set_track_mute(i, track.mix.mute)

    # Render
    print(f"=== Rendering to {output_path} ===", flush=True)
    rendered_path = reaper.render_project(
        output_path=output_path,
        start=0,
        end=song_spec.metadata.duration_seconds,
    )

    if rendered_path is None:
        print(f"=== Render failed ===", flush=True)
        return {"status": "error", "error_message": "Render failed - output file not created"}

    print(f"=== Render complete: {rendered_path} ===", flush=True)

    return {
        "status": "success",
        "rendered_path": rendered_path,
        "tracks_created": len(plan.tracks),
        "notes_inserted": total_notes,
    }


def evaluate_recreation(
    original_path: str,
    recreation_path: str,
    iteration: int = 1,
) -> dict[str, Any]:
    """Evaluate how well a recreation matches the original song.

    Use this tool after executing a plan and rendering audio to assess
    quality and get feedback for the next iteration.

    Args:
        original_path: File path to the original audio (WAV).
        recreation_path: File path to the recreated audio (WAV).
        iteration: Current iteration number.

    Returns:
        dict: Contains 'status', 'scores' (timing, harmony, melody, instruments,
              mix, overall), 'total_score', 'feedback' list, and 'stop_early' bool.
    """
    print(f"=== EVALUATE_RECREATION CALLED: iteration={iteration} ===", flush=True)
    print(f"=== original_path: {original_path} ===", flush=True)
    print(f"=== recreation_path: {recreation_path} ===", flush=True)
    if not Path(original_path).exists():
        print(f"=== ERROR: Original file not found ===", flush=True)
        return {"status": "error", "error_message": f"Original file not found: {original_path}"}
    if not Path(recreation_path).exists():
        print(f"=== ERROR: Recreation file not found ===", flush=True)
        return {"status": "error", "error_message": f"Recreation file not found: {recreation_path}"}

    print(f"=== Loading audio files for evaluation... ===", flush=True)
    try:
        print(f"=== Sending audio to Gemini for AI evaluation... ===", flush=True)
        result = _ai_evaluation(original_path, recreation_path, iteration)
        print(f"=== AI evaluation complete: {result.total_score}/{result.max_score} ===", flush=True)
        return {
            "status": "success",
            "scores": result.scores.model_dump(),
            "total_score": result.total_score,
            "max_score": result.max_score,
            "feedback": [f.model_dump() for f in result.feedback],
            "stop_early": result.stop_early,
            "stop_reason": result.stop_reason,
            "method": result.evaluation_method.value,
        }
    except Exception as e:
        logger.warning(f"AI evaluation failed: {e}, using MFCC fallback")
        result = _mfcc_fallback_evaluation(original_path, recreation_path)
        return {
            "status": "success",
            "scores": result.scores.model_dump(),
            "total_score": result.total_score,
            "max_score": result.max_score,
            "feedback": [f.model_dump() for f in result.feedback],
            "stop_early": result.stop_early,
            "stop_reason": result.stop_reason,
            "method": result.evaluation_method.value,
        }


def _build_planning_message(
    song_spec: SongSpec,
    previous_feedback: str | None,
    iteration: int,
    session_id: str | None = None,
) -> str:
    parts = [
        f"## Song Analysis (Iteration {iteration})",
        f"- Tempo: {song_spec.metadata.tempo_bpm} BPM",
        f"- Key: {song_spec.metadata.key}",
        f"- Time Signature: {song_spec.metadata.time_signature}",
        f"- Duration: {song_spec.metadata.duration_seconds:.1f} seconds",
        "",
        "## Available Stems",
    ]

    for stem_name, stem_data in song_spec.stems.items():
        parts.append(f"- {stem_name}: {stem_data.role.value}")

    parts.extend(["", "## Song Structure"])
    for section in song_spec.structure.sections:
        parts.append(f"- {section.name}: {section.start:.1f}s - {section.end:.1f}s")

    if session_id:
        cached_analysis = _get_all_cached_analysis(session_id)
        if cached_analysis:
            parts.extend(["", "## Detailed Analysis (from agentic tools)"])
            parts.append(cached_analysis)

    if previous_feedback:
        parts.extend(["", "## Previous Iteration Feedback", previous_feedback])

    parts.extend(["", "Generate an ExecutionPlan JSON to recreate this song."])
    return "\n".join(parts)


def _get_all_cached_analysis(session_id: str) -> str:
    """Format all cached analysis for planning prompt."""
    if session_id not in _analysis_cache:
        return ""

    cache = _analysis_cache[session_id]
    parts = []

    if "genre" in cache:
        g = cache["genre"]
        parts.append(f"### Genre Analysis")
        parts.append(f"- Primary Genre: {g.get('primary_genre', 'unknown')}")
        parts.append(f"- Subgenre: {g.get('subgenre', '')}")
        parts.append(f"- Aesthetic Tags: {', '.join(g.get('aesthetic_tags', []))}")
        parts.append(f"- Mood Tags: {', '.join(g.get('mood_tags', []))}")
        ps = g.get("production_style", {})
        if ps:
            parts.append(f"- Production: {'electronic' if ps.get('is_electronic') else 'acoustic'}, {ps.get('density', 'medium')} density, {ps.get('dynamics', 'moderate')} dynamics")
        parts.append("")

    for stem in ["vocals", "drums", "bass", "other"]:
        inst_key = f"instrument_{stem}"
        if inst_key in cache:
            inst = cache[inst_key]
            parts.append(f"### {stem.capitalize()} Instrument Analysis")
            parts.append(f"- Identified as: {inst.get('primary_instrument', 'unknown')} (confidence: {inst.get('confidence', 0):.0%})")
            parts.append(f"- Timbre: {', '.join(inst.get('timbre_descriptors', []))}")
            parts.append(f"- Synthetic: {inst.get('is_synthetic', False)}")
            parts.append(f"- Suggested VST: {inst.get('suggested_vst', 'Vital')} ({inst.get('suggested_preset_category', 'init')})")
            parts.append("")

        spec_key = f"spectral_{stem}"
        if spec_key in cache:
            spec = cache[spec_key]
            parts.append(f"### {stem.capitalize()} Spectral Analysis")
            parts.append(f"- Brightness: {spec.get('brightness_category', 'neutral')}")
            parts.append(f"- Warmth: {spec.get('warmth_category', 'neutral')}")
            parts.append(f"- Attack: {spec.get('attack_time_ms', 50):.0f}ms, Decay: {spec.get('decay_character', 'sustained')}")
            if spec.get("eq_suggestions"):
                parts.append(f"- EQ Suggestions: {'; '.join(spec['eq_suggestions'][:2])}")
            if spec.get("synthesis_hints"):
                parts.append(f"- Synthesis Hints: {'; '.join(spec['synthesis_hints'][:2])}")
            parts.append("")

    if "drums" in cache:
        d = cache["drums"]
        parts.append(f"### Drum Pattern Analysis")
        parts.append(f"- Overall Pattern: {d.get('overall_pattern', 'unknown')}")
        parts.append(f"- Groove: {d.get('groove_feel', 'straight')}, swing: {d.get('swing_amount', 0):.0f}%")
        kick = d.get("kick", {})
        snare = d.get("snare", {})
        hihat = d.get("hihat", {})
        parts.append(f"- Kick: {kick.get('pattern', 'unknown')} ({kick.get('density_per_bar', 0):.1f}/bar)")
        parts.append(f"- Snare: {snare.get('pattern', 'unknown')} ({snare.get('density_per_bar', 0):.1f}/bar)")
        parts.append(f"- Hi-hat: {hihat.get('pattern', 'unknown')} ({hihat.get('density_per_bar', 0):.1f}/bar)")
        parts.append("")

    if "effects" in cache:
        e = cache["effects"]
        parts.append(f"### Effects Analysis")
        rev = e.get("reverb", {})
        comp = e.get("compression", {})
        eq = e.get("eq_profile", {})
        parts.append(f"- Reverb: RT60 ~{rev.get('estimated_rt60', 0.5):.1f}s, {rev.get('room_size', 'medium')} room")
        parts.append(f"- Compression: {comp.get('compression_amount', 'moderate')}, ratio ~{comp.get('estimated_ratio', 4):.0f}:1")
        parts.append(f"- EQ Balance: {eq.get('balance', 'balanced')}")
        if rev.get("suggested_reaverb_settings"):
            s = rev["suggested_reaverb_settings"]
            parts.append(f"- ReaVerb: decay={s.get('decay', 1.0)}, wet={s.get('wet', -15)}dB")
        if comp.get("suggested_reacomp_settings"):
            s = comp["suggested_reacomp_settings"]
            parts.append(f"- ReaComp: ratio={s.get('ratio', 4)}, attack={s.get('attack', 10)}ms, threshold={s.get('threshold', -18)}dB")
        parts.append("")

    for stem in ["vocals", "drums", "bass", "other"]:
        vst_key = f"vst_{stem}"
        if vst_key in cache:
            v = cache[vst_key]
            primary = v.get("primary_vst", {})
            parts.append(f"### {stem.capitalize()} VST Recommendation")
            parts.append(f"- Use: {primary.get('name', 'Vital')} ({primary.get('preset_category', 'init')})")
            if primary.get("init_params"):
                params = ", ".join(f"{k}={v}" for k, v in list(primary["init_params"].items())[:3])
                parts.append(f"- Init Params: {params}")
            mix = v.get("mix_suggestions", {})
            parts.append(f"- Mix: {mix.get('volume_db', -6):.1f}dB, pan={mix.get('pan', 0):.1f}")
            parts.append("")

    return "\n".join(parts)


def _generate_fallback_plan(song_spec: SongSpec) -> ExecutionPlan:
    tracks = []
    role_mapping = {
        "vocals": TrackRole.VOCALS,
        "drums": TrackRole.DRUMS,
        "bass": TrackRole.BASS,
        "other": TrackRole.OTHER,
    }
    instrument_mapping = {
        "vocals": ("Vital", "Lead"),
        "drums": ("ReaSamplOmatic5000", "Kit"),
        "bass": ("Vital", "Bass"),
        "other": ("Vital", "Pad"),
    }
    volume_mapping = {"vocals": -3.0, "drums": -2.0, "bass": -4.0, "other": -6.0}

    for stem_name in song_spec.stems:
        vst, preset = instrument_mapping.get(stem_name, ("ReaSynth", "Init"))
        volume = volume_mapping.get(stem_name, -6.0)
        tracks.append(TrackPlan(
            name=f"{stem_name.capitalize()} Track",
            role=role_mapping.get(stem_name, TrackRole.OTHER),
            instrument=InstrumentConfig(vst=vst, preset=preset),
            midi_source=stem_name,
            midi_transform=None,
            mix=MixSettings(volume_db=volume, pan=0.0, mute=False),
            fx=[],
        ))

    return ExecutionPlan(
        reasoning=f"Fallback plan for {song_spec.metadata.tempo_bpm} BPM song in {song_spec.metadata.key}",
        tracks=tracks,
        master_fx=[FXConfig(plugin="ReaEQ", preset=None, params=None)],
    )


def _ai_evaluation(original_path: str, recreation_path: str, iteration: int) -> EvaluationResult:
    from google import genai
    from google.genai import types

    with open(EVALUATION_PROMPT_PATH) as f:
        system_prompt = f.read()

    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    with open(original_path, "rb") as f:
        original_audio = f.read()
    with open(recreation_path, "rb") as f:
        recreation_audio = f.read()

    user_message = f"Compare these audio files. This is iteration {iteration}."

    response = client.models.generate_content(
        model="gemini-3-pro-preview",
        contents=[
            types.Part.from_bytes(data=original_audio, mime_type="audio/wav"),
            types.Part.from_text(text="Original audio above. Recreation below:"),
            types.Part.from_bytes(data=recreation_audio, mime_type="audio/wav"),
            types.Part.from_text(text=user_message),
        ],
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
        },
    )

    eval_data = json.loads(response.text)
    return EvaluationResult.model_validate(eval_data)


def _mfcc_fallback_evaluation(original_path: str, recreation_path: str) -> EvaluationResult:
    import librosa
    from scipy.spatial.distance import cosine

    y_orig, _ = librosa.load(original_path, sr=22050)
    y_rec, _ = librosa.load(recreation_path, sr=22050)

    min_len = min(len(y_orig), len(y_rec))
    y_orig, y_rec = y_orig[:min_len], y_rec[:min_len]

    mfcc_orig = np.mean(librosa.feature.mfcc(y=y_orig, sr=22050, n_mfcc=13), axis=1)
    mfcc_rec = np.mean(librosa.feature.mfcc(y=y_rec, sr=22050, n_mfcc=13), axis=1)
    similarity = max(0, min(1, 1 - cosine(mfcc_orig, mfcc_rec)))

    base_score = int(1 + similarity * 9)

    scores = Scores(
        timing=base_score,
        harmony=base_score,
        melody=base_score,
        instruments=base_score,
        mix=base_score,
        overall=base_score,
    )
    total_score = base_score * 6

    feedback = [FeedbackItem(
        priority=1,
        category=FeedbackCategory.OTHER,
        issue=f"MFCC similarity: {similarity:.1%}",
        suggestion="Continue refining based on spectral analysis",
    )]

    return EvaluationResult(
        scores=scores,
        total_score=total_score,
        max_score=60,
        feedback=feedback,
        stop_early=total_score >= 48,
        stop_reason="Quality threshold reached" if total_score >= 48 else None,
        evaluation_method=EvaluationMethod.MFCC_FALLBACK,
    )


# =============================================================================
# AGENTIC ANALYSIS TOOLS
# =============================================================================


def analyze_genre(session_id: str, audio_path: str) -> dict[str, Any]:
    """Analyze genre and aesthetic style of the original audio.

    Call this when evaluation feedback indicates style/aesthetic mismatch
    (e.g., "wrong genre", "doesn't match the vibe", "sounds like chiptune
    instead of lo-fi hip hop").

    Results are cached in the session for use in subsequent planning.

    Args:
        session_id: Current session ID.
        audio_path: Path to the original audio file (WAV).

    Returns:
        dict with status, primary_genre, subgenre, aesthetic_tags, mood_tags,
        production_style (is_acoustic, is_electronic, density, dynamics).
    """
    print(f"=== ANALYZE_GENRE CALLED: session={session_id} ===", flush=True)

    from songclone.analysis.genre_detector import analyze_genre as _analyze_genre

    result = _analyze_genre(audio_path)

    if result.get("status") == "success":
        cache_analysis(session_id, "genre", result)

    print(f"=== ANALYZE_GENRE COMPLETE: {result.get('primary_genre', 'unknown')} ===", flush=True)
    return result


def analyze_spectral(session_id: str, stem_name: str) -> dict[str, Any]:
    """Analyze spectral/timbral characteristics of a stem.

    Call this when evaluation indicates tonal issues with a specific stem
    (e.g., "too thin", "too harsh", "too bright", "needs EQ").

    Provides actionable EQ suggestions and synthesis hints.
    Results are cached for use in planning.

    Args:
        session_id: Current session ID.
        stem_name: Stem to analyze (vocals, drums, bass, other).

    Returns:
        dict with status, brightness_category, warmth_category,
        spectral_centroid_hz, harmonic_ratio, attack_time_ms, decay_character,
        eq_suggestions, synthesis_hints.
    """
    print(f"=== ANALYZE_SPECTRAL CALLED: session={session_id}, stem={stem_name} ===", flush=True)

    if session_id not in _song_spec_store:
        return {"status": "error", "error_message": f"Session {session_id} not found"}

    song_spec = _song_spec_store[session_id]
    if stem_name not in song_spec.stems:
        return {"status": "error", "error_message": f"Stem '{stem_name}' not found in session"}

    audio_path = song_spec.stems[stem_name].audio_path

    from songclone.analysis.spectral_extractor import analyze_spectral as _analyze_spectral

    result = _analyze_spectral(audio_path, stem_name)

    if result.get("status") == "success":
        cache_analysis(session_id, f"spectral_{stem_name}", result)

    print(f"=== ANALYZE_SPECTRAL COMPLETE: {result.get('brightness_category', 'unknown')} ===", flush=True)
    return result


def analyze_instrument(session_id: str, stem_name: str) -> dict[str, Any]:
    """Identify the instrument type in a stem.

    Call this when evaluation indicates instrument type mismatch
    (e.g., "wrong instrument", "sounds synthetic when should be acoustic",
    "electric guitar sounds like synth").

    Helps the planner choose the correct VST and preset.
    Results are cached for use in planning and recommend_vst.

    Args:
        session_id: Current session ID.
        stem_name: Stem to analyze (vocals, drums, bass, other).

    Returns:
        dict with status, primary_instrument, confidence, secondary_instruments,
        timbre_descriptors, is_synthetic, suggested_vst, suggested_preset_category.
    """
    print(f"=== ANALYZE_INSTRUMENT CALLED: session={session_id}, stem={stem_name} ===", flush=True)

    if session_id not in _song_spec_store:
        return {"status": "error", "error_message": f"Session {session_id} not found"}

    song_spec = _song_spec_store[session_id]
    if stem_name not in song_spec.stems:
        return {"status": "error", "error_message": f"Stem '{stem_name}' not found in session"}

    audio_path = song_spec.stems[stem_name].audio_path

    from songclone.analysis.instrument_classifier import analyze_instrument as _analyze_instrument

    result = _analyze_instrument(audio_path, stem_name)

    if result.get("status") == "success":
        cache_analysis(session_id, f"instrument_{stem_name}", result)

    print(f"=== ANALYZE_INSTRUMENT COMPLETE: {result.get('primary_instrument', 'unknown')} ===", flush=True)
    return result


def decompose_drums(session_id: str) -> dict[str, Any]:
    """Decompose drum stem into kick/snare/hihat patterns.

    Call this when evaluation indicates drum issues (e.g., "drums sound wrong",
    "kick/snare timing off", "hat pattern incorrect").

    Replaces the monophonic drum MIDI with separate patterns for each drum element.
    The new MIDI data is stored in the session for the next execution.

    Args:
        session_id: Current session ID.

    Returns:
        dict with status, kick, snare, hihat patterns (hit_count, density_per_bar, pattern),
        overall_pattern, groove_feel, swing_amount, midi_updated flag.
    """
    print(f"=== DECOMPOSE_DRUMS CALLED: session={session_id} ===", flush=True)

    if session_id not in _song_spec_store:
        return {"status": "error", "error_message": f"Session {session_id} not found"}

    song_spec = _song_spec_store[session_id]
    if "drums" not in song_spec.stems:
        return {"status": "error", "error_message": "Drums stem not found in session"}

    audio_path = song_spec.stems["drums"].audio_path

    from songclone.analysis.drum_decomposer import decompose_drums as _decompose_drums

    result = _decompose_drums(audio_path, session_id)

    if result.get("status") == "success":
        cache_analysis(session_id, "drums", result)

    print(f"=== DECOMPOSE_DRUMS COMPLETE: {result.get('overall_pattern', 'unknown')} ===", flush=True)
    return result


def analyze_effects(session_id: str) -> dict[str, Any]:
    """Analyze reverb, compression, and EQ characteristics of the original.

    Call this when evaluation indicates mix/effects issues (e.g., "too dry",
    "wrong reverb", "needs compression", "mix balance off").

    Provides specific parameter suggestions for ReaVerb, ReaComp, ReaEQ.

    Args:
        session_id: Current session ID.

    Returns:
        dict with status, reverb (RT60, room_size, wet_dry, suggested_reaverb_settings),
        compression (dynamic_range_db, crest_factor, estimated_ratio, suggested_reacomp_settings),
        eq_profile (spectral_centroid_hz, bass_energy_db, suggested_reaeq_bands).
    """
    print(f"=== ANALYZE_EFFECTS CALLED: session={session_id} ===", flush=True)

    if session_id not in _song_spec_store:
        return {"status": "error", "error_message": f"Session {session_id} not found"}

    song_spec = _song_spec_store[session_id]

    original_path = None
    for stem_name in ["other", "vocals", "bass"]:
        if stem_name in song_spec.stems:
            original_path = song_spec.stems[stem_name].audio_path
            break

    if not original_path:
        return {"status": "error", "error_message": "No suitable stem found for effects analysis"}

    from songclone.analysis.effects_analyzer import analyze_effects as _analyze_effects

    result = _analyze_effects(original_path)

    if result.get("status") == "success":
        cache_analysis(session_id, "effects", result)

    print(f"=== ANALYZE_EFFECTS COMPLETE ===", flush=True)
    return result


def recommend_vst(session_id: str, stem_name: str) -> dict[str, Any]:
    """Recommend VST and settings based on cached analysis.

    Call this after analyze_genre and/or analyze_instrument to get
    specific VST recommendations. Uses cached analysis results.

    Args:
        session_id: Current session ID.
        stem_name: Stem to get recommendations for (vocals, drums, bass, other).

    Returns:
        dict with status, primary_vst (name, preset_category, init_params),
        fallback_vst, effects_chain, mix_suggestions, reasoning.
    """
    print(f"=== RECOMMEND_VST CALLED: session={session_id}, stem={stem_name} ===", flush=True)

    from songclone.analysis.vst_recommender import recommend_vst as _recommend_vst

    result = _recommend_vst(session_id, stem_name)

    if result.get("status") == "success":
        cache_analysis(session_id, f"vst_{stem_name}", result)

    print(f"=== RECOMMEND_VST COMPLETE: {result.get('primary_vst', {}).get('name', 'unknown')} ===", flush=True)
    return result
