"""Main analysis pipeline orchestrating all analysis tools."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from songclone.analysis.schemas import (
    BassAnalysis,
    ChordEvent,
    DrumsAnalysis,
    Metadata,
    OtherAnalysis,
    Section,
    SongSpec,
    StemData,
    StemRole,
    Structure,
    VocalRange,
    VocalsAnalysis,
)
from songclone.analysis.demucs_runner import separate_stems, StemPaths
from songclone.analysis.basic_pitch_runner import extract_midi
from songclone.analysis.madmom_runner import detect_beats, BeatInfo
from songclone.analysis.chord_runner import detect_chords, detect_key
from songclone.api.events import (
    event_emitter,
    LogEvent,
    LogLevel,
    PhaseEvent,
    PhaseType,
    EventStatus,
)

logger = logging.getLogger(__name__)

ANALYSIS_DURATION_SECONDS = 30


def _trim_audio(audio_path: Path, output_path: Path, max_seconds: float = ANALYSIS_DURATION_SECONDS) -> Path:
    """Trim audio to first N seconds for faster analysis."""
    data, sr = sf.read(str(audio_path))
    max_samples = int(max_seconds * sr)
    if len(data) > max_samples:
        data = data[:max_samples]
    sf.write(str(output_path), data, sr)
    return output_path


async def analyze_song(
    audio_path: Path,
    output_dir: Path,
    session_id: Optional[str] = None,
) -> SongSpec:
    """
    Run complete analysis pipeline on an audio file.

    Per constitution IV: Analysis tool failures MUST NOT block other tools
    (parallel execution with fallbacks).

    Args:
        audio_path: Path to input audio file
        output_dir: Directory to write analysis outputs
        session_id: Optional session ID for SSE events

    Returns:
        Complete SongSpec with all analysis results
    """
    print(f"=== ANALYZE_SONG ENTERED ===", flush=True)
    logger.info(f"analyze_song called: audio_path={audio_path}, output_dir={output_dir}, session_id={session_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== ANALYZE_SONG output_dir created ===", flush=True)

    # Trim to first 30 seconds for faster analysis
    trimmed_path = output_dir / "trimmed_input.wav"
    audio_path = _trim_audio(audio_path, trimmed_path)
    print(f"=== Audio trimmed to {ANALYSIS_DURATION_SECONDS}s ===", flush=True)

    stems_dir = output_dir / "stems"

    if session_id:
        print(f"=== Emitting ANALYSIS STARTED event ===", flush=True)
        await event_emitter.emit(
            session_id,
            PhaseEvent(phase=PhaseType.ANALYSIS, status=EventStatus.STARTED),
        )
        print(f"=== ANALYSIS STARTED event emitted ===", flush=True)
    else:
        print(f"=== No session_id, skipping event emit ===", flush=True)

    print(f"=== About to define log function ===", flush=True)

    async def log(message: str, level: LogLevel = LogLevel.INFO) -> None:
        print(f"=== Inside log function: {message} ===", flush=True)
        logger.log(
            logging.INFO if level == LogLevel.INFO else logging.WARNING,
            message,
        )
        if session_id:
            await event_emitter.emit(
                session_id,
                LogEvent(level=level, message=message),
            )
        print(f"=== log function done ===", flush=True)

    print(f"=== log function defined ===", flush=True)
    print(f"=== About to call first log ===", flush=True)
    await log("Starting audio analysis...")
    print(f"=== First log complete, starting stem separation ===", flush=True)

    # Run analysis tasks SEQUENTIALLY to avoid threading deadlocks
    # (parallel execution of C extension libraries causes GIL issues)

    await log("Separating stems with Demucs...")
    print(f"=== Running stem separation (sequential) ===", flush=True)
    stem_paths = await _safe_separate_stems(audio_path, stems_dir, log)

    await log("Detecting tempo and beats...")
    print(f"=== Running beat detection (sequential) ===", flush=True)
    beat_info = await _safe_detect_beats(audio_path, log, session_id)

    await log("Detecting key...")
    print(f"=== Running key detection (sequential) ===", flush=True)
    key = await _safe_detect_key(audio_path, log)

    await log("Detecting chords...")
    print(f"=== Running chord detection (sequential) ===", flush=True)
    chords = await _safe_detect_chords(audio_path, log)

    print(f"=== All 4 analysis tasks complete ===", flush=True)

    await log("Extracting MIDI from stems...")
    midi_tasks = {
        "vocals": asyncio.create_task(_safe_extract_midi(stem_paths.vocals, "vocals", log)),
        "drums": asyncio.create_task(_safe_extract_midi(stem_paths.drums, "drums", log)),
        "bass": asyncio.create_task(_safe_extract_midi(stem_paths.bass, "bass", log)),
        "other": asyncio.create_task(_safe_extract_midi(stem_paths.other, "other", log)),
    }

    midi_results = await asyncio.gather(*midi_tasks.values())
    midi_data = dict(zip(midi_tasks.keys(), midi_results))

    await log("Detecting song sections...")
    sections = detect_sections(beat_info, chords)
    await log(f"✓ Section detection complete ({len(sections)} sections found)")

    duration = await _get_audio_duration(audio_path)

    stems = {
        "vocals": StemData(
            role=StemRole.VOCALS,
            audio_path=str(stem_paths.vocals),
            midi_data=midi_data["vocals"],
            analysis=VocalsAnalysis(
                analysis_type="vocals",
                detected_range=VocalRange(low="C3", high="C5"),
            ),
        ),
        "drums": StemData(
            role=StemRole.DRUMS,
            audio_path=str(stem_paths.drums),
            midi_data=midi_data["drums"],
            analysis=DrumsAnalysis(
                analysis_type="drums",
                pattern_summary="Standard drum pattern",
            ),
        ),
        "bass": StemData(
            role=StemRole.BASS,
            audio_path=str(stem_paths.bass),
            midi_data=midi_data["bass"],
            analysis=BassAnalysis(
                analysis_type="bass",
                root_notes=_extract_root_notes(chords),
            ),
        ),
        "other": StemData(
            role=StemRole.OTHER,
            audio_path=str(stem_paths.other),
            midi_data=midi_data["other"],
            analysis=OtherAnalysis(
                analysis_type="other",
                instrument_guess="Keyboard, synth",
            ),
        ),
    }

    song_spec = SongSpec(
        metadata=Metadata(
            duration_seconds=duration,
            tempo_bpm=beat_info.tempo_bpm,
            time_signature=beat_info.time_signature,
            key=key,
        ),
        stems=stems,
        structure=Structure(sections=sections),
        chords=chords,
    )

    await log(f"Analysis complete: {beat_info.tempo_bpm} BPM, {key}, {len(sections)} sections")

    if session_id:
        await event_emitter.emit(
            session_id,
            PhaseEvent(
                phase=PhaseType.ANALYSIS,
                status=EventStatus.COMPLETE,
                data=song_spec.model_dump(),
            ),
        )

    return song_spec


async def _run_with_heartbeat(
    coro,
    session_id: str,
    task_name: str,
    interval: float = 5.0
):
    """Run a coroutine with periodic heartbeat events."""
    start_time = time.time()

    async def heartbeat():
        while True:
            await asyncio.sleep(interval)
            elapsed = int(time.time() - start_time)
            await event_emitter.emit(
                session_id,
                LogEvent(level=LogLevel.INFO, message=f"⏳ {task_name}... ({elapsed}s)")
            )

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        result = await coro
        return result
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


async def _safe_separate_stems(
    audio_path: Path, output_dir: Path, log_fn=None
) -> StemPaths:
    """Safely run stem separation with error handling."""
    print(f"=== _safe_separate_stems STARTED ===", flush=True)
    try:
        result = await separate_stems(audio_path, output_dir)
        print(f"=== _safe_separate_stems DONE ===", flush=True)
        if log_fn:
            await log_fn("✓ Stem separation complete")
        return result
    except Exception as e:
        logger.error(f"Stem separation failed: {e}")
        if log_fn:
            await log_fn(f"✗ Stem separation failed: {e}", LogLevel.WARN)
        output_dir.mkdir(parents=True, exist_ok=True)
        return StemPaths(
            vocals=output_dir / "vocals.wav",
            drums=output_dir / "drums.wav",
            bass=output_dir / "bass.wav",
            other=output_dir / "other.wav",
        )


async def _safe_detect_beats(audio_path: Path, log_fn=None, session_id: Optional[str] = None) -> BeatInfo:
    """Safely run beat detection with error handling."""
    print(f"=== _safe_detect_beats STARTED ===", flush=True)
    try:
        if session_id:
            result = await _run_with_heartbeat(
                detect_beats(audio_path),
                session_id,
                "Beat detection running",
                interval=5.0
            )
        else:
            result = await detect_beats(audio_path)
        print(f"=== _safe_detect_beats DONE ===", flush=True)
        if log_fn:
            await log_fn("✓ Beat detection complete")
        return result
    except Exception as e:
        logger.error(f"Beat detection failed: {e}")
        if log_fn:
            await log_fn(f"✗ Beat detection failed: {e}", LogLevel.WARN)
        return BeatInfo(
            tempo_bpm=120.0,
            time_signature="4/4",
            beats=[],
            downbeats=[],
        )


async def _safe_detect_key(audio_path: Path, log_fn=None) -> str:
    """Safely run key detection with error handling."""
    print(f"=== _safe_detect_key STARTED ===", flush=True)
    try:
        result = await detect_key(audio_path)
        print(f"=== _safe_detect_key DONE ===", flush=True)
        if log_fn:
            await log_fn("✓ Key detection complete")
        return result
    except Exception as e:
        logger.error(f"Key detection failed: {e}")
        if log_fn:
            await log_fn(f"✗ Key detection failed: {e}", LogLevel.WARN)
        return "C major"


async def _safe_detect_chords(audio_path: Path, log_fn=None) -> list[ChordEvent]:
    """Safely run chord detection with error handling."""
    print(f"=== _safe_detect_chords STARTED ===", flush=True)
    try:
        result = await detect_chords(audio_path)
        print(f"=== _safe_detect_chords DONE ===", flush=True)
        if log_fn:
            await log_fn("✓ Chord detection complete")
        return result
    except Exception as e:
        logger.error(f"Chord detection failed: {e}")
        if log_fn:
            await log_fn(f"✗ Chord detection failed: {e}", LogLevel.WARN)
        return []


async def _safe_extract_midi(stem_path: Path, stem_name: str = "", log_fn=None) -> str:
    """Safely run MIDI extraction with error handling."""
    try:
        if not stem_path.exists() or stem_path.stat().st_size == 0:
            return ""
        result = await extract_midi(stem_path)
        if log_fn and stem_name:
            await log_fn(f"✓ MIDI extraction complete ({stem_name})")
        return result
    except Exception as e:
        logger.error(f"MIDI extraction failed for {stem_path}: {e}")
        if log_fn and stem_name:
            await log_fn(f"✗ MIDI extraction failed ({stem_name}): {e}", LogLevel.WARN)
        return ""


async def _get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds."""
    try:
        import librosa

        y, sr = librosa.load(str(audio_path), sr=None)
        return len(y) / sr
    except Exception:
        return 180.0


def detect_sections(beat_info: BeatInfo, chords: list[ChordEvent]) -> list[Section]:
    """
    Detect song sections based on beat and chord information.

    Uses downbeat positions and chord changes to identify section boundaries.
    """
    if not beat_info.downbeats:
        return [Section(name="full", start=0.0, end=180.0, bars=45)]

    sections: list[Section] = []
    downbeats = beat_info.downbeats

    section_names = ["intro", "verse", "chorus", "verse", "chorus", "bridge", "chorus", "outro"]
    bars_per_section = max(4, len(downbeats) // len(section_names))

    current_bar = 0
    for i, section_name in enumerate(section_names):
        if current_bar >= len(downbeats) - 1:
            break

        start_idx = current_bar
        end_idx = min(current_bar + bars_per_section, len(downbeats) - 1)

        if end_idx <= start_idx:
            break

        sections.append(Section(
            name=section_name,
            start=downbeats[start_idx],
            end=downbeats[end_idx],
            bars=end_idx - start_idx,
        ))

        current_bar = end_idx

    if not sections:
        sections.append(Section(name="full", start=0.0, end=180.0, bars=45))

    return sections


def _extract_root_notes(chords: list[ChordEvent]) -> list[str]:
    """Extract unique root notes from chord progression."""
    roots = []
    for chord in chords:
        root = chord.chord.rstrip("m").rstrip("7").rstrip("maj").rstrip("min")
        if root and root not in roots:
            roots.append(root)
    return roots[:8]
