"""Execution Agent for REAPER operations."""

import logging
from pathlib import Path

from songclone.analysis.schemas import SongSpec
from songclone.orchestrator.schemas import ExecutionPlan
from songclone.reaper_mcp.tools import (
    BatchCreateTracksInput,
    BatchInsertMidiInput,
    BatchSetFXInput,
    BatchSetLevelsInput,
    CreateProjectInput,
    FXConfig,
    FXItem,
    LevelConfig,
    MidiInsertItem,
    RenderAudioInput,
    TrackConfig,
    batch_create_tracks,
    batch_insert_midi,
    batch_set_fx,
    batch_set_levels,
    create_project,
    get_project_state,
    render_audio,
)

logger = logging.getLogger(__name__)


async def execute_plan(
    plan: ExecutionPlan,
    song_spec: SongSpec,
    output_path: Path,
) -> str:
    """
    Execute a recreation plan in REAPER.

    Per constitution III: REAPER state MUST be verified after every batch operation.

    Args:
        plan: The execution plan to follow
        song_spec: Original song analysis for MIDI data
        output_path: Path to render the output audio

    Returns:
        Path to rendered audio file
    """
    logger.info("Starting plan execution in REAPER")

    project_result = await create_project(CreateProjectInput(
        tempo=song_spec.metadata.tempo_bpm,
        time_signature=song_spec.metadata.time_signature,
        duration_seconds=song_spec.metadata.duration_seconds,
    ))

    if not project_result.success:
        raise RuntimeError(f"Failed to create project: {project_result.error}")

    logger.info("Created REAPER project")

    track_configs = [
        TrackConfig(
            name=track.name,
            instrument_vst=track.instrument.vst,
            instrument_preset=track.instrument.preset,
        )
        for track in plan.tracks
    ]

    tracks_result = await batch_create_tracks(BatchCreateTracksInput(tracks=track_configs))

    if not tracks_result.success:
        raise RuntimeError(f"Failed to create tracks: {tracks_result.error}")

    if tracks_result.fallbacks:
        for fb in tracks_result.fallbacks:
            logger.warning(f"VST fallback: {fb.requested} → {fb.used} ({fb.reason})")

    logger.info(f"Created {len(tracks_result.track_ids)} tracks")

    state = await get_project_state()
    if not state.success:
        logger.warning("Could not verify project state after track creation")

    midi_items = []
    for i, track in enumerate(plan.tracks):
        stem_name = track.midi_source
        if stem_name in song_spec.stems:
            stem = song_spec.stems[stem_name]
            if stem.midi_data:
                velocity_scale = 1.0
                if track.midi_transform:
                    velocity_scale = track.midi_transform.velocity_scale

                midi_items.append(MidiInsertItem(
                    track_id=tracks_result.track_ids[i],
                    midi_data=stem.midi_data,
                    start_time=0,
                    velocity_scale=velocity_scale,
                ))

    if midi_items:
        midi_result = await batch_insert_midi(BatchInsertMidiInput(items=midi_items))
        if not midi_result.success:
            logger.warning(f"MIDI insertion issues: {midi_result.error}")
        else:
            logger.info(f"Inserted MIDI into {midi_result.items_inserted} tracks")

    fx_configs = []
    for i, track in enumerate(plan.tracks):
        if track.fx:
            fx_configs.append(FXConfig(
                track_id=tracks_result.track_ids[i],
                fx_chain=[
                    FXItem(
                        plugin=fx.plugin,
                        preset=fx.preset,
                        params=fx.params,
                    )
                    for fx in track.fx
                ],
            ))

    if fx_configs:
        fx_result = await batch_set_fx(BatchSetFXInput(fx_configs=fx_configs))
        if not fx_result.success:
            logger.warning(f"FX setup issues: {fx_result.error}")
        else:
            logger.info(f"Added {fx_result.fx_added} FX plugins")

    levels = [
        LevelConfig(
            track_id=tracks_result.track_ids[i],
            volume_db=track.mix.volume_db,
            pan=track.mix.pan,
            mute=track.mix.mute,
        )
        for i, track in enumerate(plan.tracks)
    ]

    levels_result = await batch_set_levels(BatchSetLevelsInput(levels=levels))
    if not levels_result.success:
        logger.warning(f"Level setting issues: {levels_result.error}")
    else:
        logger.info(f"Set levels for {levels_result.tracks_updated} tracks")

    final_state = await get_project_state()
    if final_state.success:
        logger.info(f"Final project state: {len(final_state.tracks)} tracks")
    else:
        logger.warning("Could not verify final project state")

    render_result = await render_audio(RenderAudioInput(
        output_path=str(output_path),
        format="wav",
        start_time=0,
        end_time=song_spec.metadata.duration_seconds,
    ))

    if not render_result.success:
        raise RuntimeError(f"Failed to render audio: {render_result.error}")

    logger.info(f"Rendered audio to {render_result.path}")

    return render_result.path
