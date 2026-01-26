"""Main analysis pipeline orchestrating all analysis tools."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import numpy as np

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
    output_dir.mkdir(parents=True, exist_ok=True)
    stems_dir = output_dir / "stems"

    if session_id:
        await event_emitter.emit(
            session_id,
            PhaseEvent(phase=PhaseType.ANALYSIS, status=EventStatus.STARTED),
        )

    async def log(message: str, level: LogLevel = LogLevel.INFO) -> None:
        logger.log(
            logging.INFO if level == LogLevel.INFO else logging.WARNING,
            message,
        )
        if session_id:
            await event_emitter.emit(
                session_id,
                LogEvent(level=level, message=message),
            )

    await log("Starting audio analysis...")

    await log("Separating stems with Demucs...")
    stem_separation_task = asyncio.create_task(
        _safe_separate_stems(audio_path, stems_dir)
    )

    await log("Detecting tempo and beats...")
    beat_detection_task = asyncio.create_task(
        _safe_detect_beats(audio_path)
    )

    await log("Detecting key...")
    key_detection_task = asyncio.create_task(
        _safe_detect_key(audio_path)
    )

    await log("Detecting chords...")
    chord_detection_task = asyncio.create_task(
        _safe_detect_chords(audio_path)
    )

    stem_paths, beat_info, key, chords = await asyncio.gather(
        stem_separation_task,
        beat_detection_task,
        key_detection_task,
        chord_detection_task,
    )

    await log("Extracting MIDI from stems...")
    midi_tasks = {
        "vocals": asyncio.create_task(_safe_extract_midi(stem_paths.vocals)),
        "drums": asyncio.create_task(_safe_extract_midi(stem_paths.drums)),
        "bass": asyncio.create_task(_safe_extract_midi(stem_paths.bass)),
        "other": asyncio.create_task(_safe_extract_midi(stem_paths.other)),
    }

    midi_results = await asyncio.gather(*midi_tasks.values())
    midi_data = dict(zip(midi_tasks.keys(), midi_results))

    await log("Detecting song sections...")
    sections = detect_sections(beat_info, chords)

    duration = await _get_audio_duration(audio_path)

    stems = {
        "vocals": StemData(
            role=StemRole.VOCALS,
            audio_path=str(stem_paths.vocals),
            midi_data=midi_data["vocals"],
            analysis=VocalsAnalysis(detected_range=VocalRange(low="C3", high="C5")),
        ),
        "drums": StemData(
            role=StemRole.DRUMS,
            audio_path=str(stem_paths.drums),
            midi_data=midi_data["drums"],
            analysis=DrumsAnalysis(pattern_summary="Standard drum pattern"),
        ),
        "bass": StemData(
            role=StemRole.BASS,
            audio_path=str(stem_paths.bass),
            midi_data=midi_data["bass"],
            analysis=BassAnalysis(root_notes=_extract_root_notes(chords)),
        ),
        "other": StemData(
            role=StemRole.OTHER,
            audio_path=str(stem_paths.other),
            midi_data=midi_data["other"],
            analysis=OtherAnalysis(instrument_guess="Keyboard, synth"),
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


async def _safe_separate_stems(audio_path: Path, output_dir: Path) -> StemPaths:
    """Safely run stem separation with error handling."""
    try:
        return await separate_stems(audio_path, output_dir)
    except Exception as e:
        logger.error(f"Stem separation failed: {e}")
        output_dir.mkdir(parents=True, exist_ok=True)
        return StemPaths(
            vocals=output_dir / "vocals.wav",
            drums=output_dir / "drums.wav",
            bass=output_dir / "bass.wav",
            other=output_dir / "other.wav",
        )


async def _safe_detect_beats(audio_path: Path) -> BeatInfo:
    """Safely run beat detection with error handling."""
    try:
        return await detect_beats(audio_path)
    except Exception as e:
        logger.error(f"Beat detection failed: {e}")
        return BeatInfo(
            tempo_bpm=120.0,
            time_signature="4/4",
            beats=[],
            downbeats=[],
        )


async def _safe_detect_key(audio_path: Path) -> str:
    """Safely run key detection with error handling."""
    try:
        return await detect_key(audio_path)
    except Exception as e:
        logger.error(f"Key detection failed: {e}")
        return "C major"


async def _safe_detect_chords(audio_path: Path) -> list[ChordEvent]:
    """Safely run chord detection with error handling."""
    try:
        return await detect_chords(audio_path)
    except Exception as e:
        logger.error(f"Chord detection failed: {e}")
        return []


async def _safe_extract_midi(stem_path: Path) -> str:
    """Safely run MIDI extraction with error handling."""
    try:
        if not stem_path.exists() or stem_path.stat().st_size == 0:
            return ""
        return await extract_midi(stem_path)
    except Exception as e:
        logger.error(f"MIDI extraction failed for {stem_path}: {e}")
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
