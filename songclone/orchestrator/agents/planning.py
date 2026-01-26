"""Planning Agent for song recreation."""

import json
import logging
import os
from pathlib import Path

from songclone.analysis.schemas import SongSpec
from songclone.orchestrator.schemas import ExecutionPlan

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "planning.txt"


def load_system_prompt() -> str:
    """Load the planning system prompt."""
    with open(PROMPT_PATH) as f:
        return f.read()


async def generate_plan(
    song_spec: SongSpec,
    previous_evaluation: dict | None = None,
    iteration: int = 1,
) -> ExecutionPlan:
    """
    Generate an execution plan for recreating a song.

    Per constitution VIII: thinking_level="high" for planning tasks.

    Args:
        song_spec: Analysis output with tempo, key, stems, etc.
        previous_evaluation: Feedback from previous iteration (if any)
        iteration: Current iteration number

    Returns:
        ExecutionPlan with tracks, instruments, mix settings
    """
    system_prompt = load_system_prompt()

    user_message = _build_user_message(song_spec, previous_evaluation, iteration)

    try:
        from google import genai

        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=user_message,
            config={
                "system_instruction": system_prompt,
                "thinking_config": {"thinking_level": "high"},
                "response_mime_type": "application/json",
            },
        )

        plan_data = json.loads(response.text)
        return ExecutionPlan.model_validate(plan_data)

    except ImportError:
        logger.warning("google-genai not available, using fallback plan")
        return _generate_fallback_plan(song_spec)
    except Exception as e:
        logger.error(f"Planning agent failed: {e}")
        return _generate_fallback_plan(song_spec)


def _build_user_message(
    song_spec: SongSpec,
    previous_evaluation: dict | None,
    iteration: int,
) -> str:
    """Build the user message for the planning agent."""
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
        if stem_data.analysis:
            parts.append(f"  Analysis: {stem_data.analysis}")

    parts.extend([
        "",
        "## Song Structure",
    ])

    for section in song_spec.structure.sections:
        parts.append(f"- {section.name}: {section.start:.1f}s - {section.end:.1f}s ({section.bars} bars)")

    if song_spec.chords:
        parts.extend([
            "",
            "## Chord Progression",
        ])
        chord_summary = ", ".join(c.chord for c in song_spec.chords[:8])
        if len(song_spec.chords) > 8:
            chord_summary += "..."
        parts.append(chord_summary)

    if previous_evaluation:
        parts.extend([
            "",
            "## Previous Iteration Feedback",
            f"Total Score: {previous_evaluation.get('total_score', 'N/A')}/60",
            "",
            "Feedback to address:",
        ])

        feedback_items = previous_evaluation.get("feedback", [])
        for item in feedback_items[:5]:
            parts.append(f"- [{item.get('category')}] {item.get('issue')}")
            parts.append(f"  Suggestion: {item.get('suggestion')}")

    parts.extend([
        "",
        "Generate an ExecutionPlan JSON to recreate this song.",
    ])

    return "\n".join(parts)


def _generate_fallback_plan(song_spec: SongSpec) -> ExecutionPlan:
    """Generate a basic fallback plan when AI is unavailable."""
    from songclone.orchestrator.schemas import (
        ExecutionPlan,
        FXConfig,
        InstrumentConfig,
        MixSettings,
        TrackPlan,
        TrackRole,
    )

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

    volume_mapping = {
        "vocals": -3.0,
        "drums": -2.0,
        "bass": -4.0,
        "other": -6.0,
    }

    for stem_name, stem_data in song_spec.stems.items():
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
        master_fx=[
            FXConfig(plugin="ReaEQ", preset=None, params=None),
            FXConfig(plugin="ReaComp", preset=None, params={"ratio": 2}),
        ],
    )
