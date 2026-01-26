"""Integration tests for the orchestrator agentic loop.

Tests a single iteration cycle with mocked REAPER to verify
the plan → execute → evaluate workflow.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from songclone.analysis.schemas import (
    ChordEvent,
    Metadata,
    Section,
    SongSpec,
    StemData,
    StemRole,
    Structure,
)
from songclone.api.events import event_emitter
from songclone.api.schemas import Session, SessionStatus
from songclone.orchestrator.main import run_recreation_loop
from songclone.orchestrator.schemas import (
    EvaluationMethod,
    EvaluationResult,
    ExecutionPlan,
    FeedbackCategory,
    FeedbackItem,
    Scores,
)


@pytest.fixture
def mock_song_spec() -> SongSpec:
    """Create a mock SongSpec for testing."""
    return SongSpec(
        metadata=Metadata(
            duration_seconds=180.0,
            tempo_bpm=120.0,
            time_signature="4/4",
            key="C major",
        ),
        stems={
            "vocals": StemData(
                role=StemRole.VOCALS,
                audio_path="/tmp/vocals.wav",
                midi_data="base64encodedmidi",
                analysis=None,
            ),
            "drums": StemData(
                role=StemRole.DRUMS,
                audio_path="/tmp/drums.wav",
                midi_data="base64encodedmidi",
                analysis=None,
            ),
            "bass": StemData(
                role=StemRole.BASS,
                audio_path="/tmp/bass.wav",
                midi_data="base64encodedmidi",
                analysis=None,
            ),
            "other": StemData(
                role=StemRole.OTHER,
                audio_path="/tmp/other.wav",
                midi_data="base64encodedmidi",
                analysis=None,
            ),
        },
        structure=Structure(
            sections=[
                Section(name="intro", start=0.0, end=15.0, bars=4),
                Section(name="verse", start=15.0, end=45.0, bars=8),
            ]
        ),
        chords=[
            ChordEvent(time=0.0, duration=4.0, chord="C"),
            ChordEvent(time=4.0, duration=4.0, chord="G"),
        ],
    )


@pytest.fixture
def mock_session(mock_song_spec: SongSpec, tmp_path: Path) -> Session:
    """Create a mock session for testing."""
    # Create session directory structure
    session_id = "test-session-orchestrator"
    session_dir = tmp_path / "sessions" / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "iterations").mkdir()

    # Create a mock original audio file
    original_audio = session_dir / "original.wav"
    original_audio.write_bytes(b"RIFF" + b"\x00" * 100)  # Minimal WAV header

    return Session(
        id=session_id,
        status=SessionStatus.ANALYZING,
        original_audio_path=str(original_audio),
        song_spec=mock_song_spec,
        iterations=[],
        current_iteration=0,
        max_iterations=2,
        quality_threshold=0.8,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


class TestOrchestratorLoopSingleIteration:
    """Test a single iteration of the orchestrator loop."""

    @pytest.mark.asyncio
    async def test_orchestrator_emits_iteration_events(
        self, mock_session: Session, tmp_path: Path
    ) -> None:
        """Test that orchestrator emits correct SSE events during iteration."""
        session_id = mock_session.id
        queue = event_emitter.subscribe(session_id)

        # Mock the agents to avoid actual AI calls and REAPER interaction
        mock_plan = ExecutionPlan(
            reasoning="Test plan for mocked iteration",
            tracks=[],
            master_fx=[],
        )

        mock_evaluation = EvaluationResult(
            scores=Scores(
                timing=8,
                harmony=7,
                melody=7,
                instruments=7,
                mix=6,
                overall=7,
            ),
            total_score=42,
            max_score=60,
            feedback=[
                FeedbackItem(
                    priority=1,
                    category=FeedbackCategory.MIX,
                    issue="Mix needs work",
                    suggestion="Adjust levels",
                )
            ],
            stop_early=False,
            stop_reason=None,
            evaluation_method=EvaluationMethod.MFCC_FALLBACK,
        )

        with patch("songclone.orchestrator.main.generate_plan", new_callable=AsyncMock) as mock_generate_plan, \
             patch("songclone.orchestrator.main.execute_plan", new_callable=AsyncMock) as mock_execute_plan, \
             patch("songclone.orchestrator.main.evaluate_recreation", new_callable=AsyncMock) as mock_evaluate, \
             patch("songclone.orchestrator.main.get_original_audio_path") as mock_orig_path, \
             patch("songclone.orchestrator.main.get_iteration_render_path") as mock_render_path, \
             patch("songclone.orchestrator.main.save_session"):

            mock_generate_plan.return_value = mock_plan
            mock_execute_plan.return_value = "/tmp/render.wav"
            mock_evaluate.return_value = mock_evaluation
            mock_orig_path.return_value = Path(mock_session.original_audio_path)
            mock_render_path.return_value = tmp_path / "render.wav"

            # High score to trigger early stop on second iteration
            mock_evaluation_high = EvaluationResult(
                scores=Scores(
                    timing=9, harmony=9, melody=9, instruments=8, mix=8, overall=9
                ),
                total_score=52,
                max_score=60,
                feedback=[],
                stop_early=True,
                stop_reason="Quality threshold (80%) reached",
                evaluation_method=EvaluationMethod.AI,
            )
            mock_evaluate.side_effect = [mock_evaluation, mock_evaluation_high]

            try:
                # Run the orchestrator in background
                task = asyncio.create_task(run_recreation_loop(mock_session))

                # Collect events
                events = []
                try:
                    while True:
                        event = await asyncio.wait_for(queue.get(), timeout=10.0)
                        events.append(event)

                        # Stop when we see complete event
                        if event.type == "complete":
                            break
                except asyncio.TimeoutError:
                    pass

                await task

                # Verify event sequence
                event_types = [e.type for e in events]

                # Should have phase, iteration, step events
                assert "phase" in event_types
                assert "iteration" in event_types
                assert "step" in event_types
                assert "complete" in event_types

                # Find iteration events
                iteration_events = [e for e in events if e.type == "iteration"]
                assert len(iteration_events) >= 2  # At least start and complete

                # Find step events
                step_events = [e for e in events if e.type == "step"]
                step_names = [e.step.value for e in step_events]
                assert "planning" in step_names
                assert "execution" in step_names
                assert "evaluation" in step_names

            finally:
                event_emitter.unsubscribe(session_id, queue)

    @pytest.mark.asyncio
    async def test_orchestrator_stops_at_quality_threshold(
        self, mock_session: Session, tmp_path: Path
    ) -> None:
        """Test that orchestrator stops when quality threshold is reached."""
        mock_plan = ExecutionPlan(
            reasoning="Test plan",
            tracks=[],
            master_fx=[],
        )

        mock_evaluation = EvaluationResult(
            scores=Scores(
                timing=9, harmony=9, melody=9, instruments=8, mix=8, overall=9
            ),
            total_score=52,  # Above 80% of 60
            max_score=60,
            feedback=[],
            stop_early=True,
            stop_reason="Quality threshold (80%) reached",
            evaluation_method=EvaluationMethod.AI,
        )

        with patch("songclone.orchestrator.main.generate_plan", new_callable=AsyncMock) as mock_generate_plan, \
             patch("songclone.orchestrator.main.execute_plan", new_callable=AsyncMock) as mock_execute_plan, \
             patch("songclone.orchestrator.main.evaluate_recreation", new_callable=AsyncMock) as mock_evaluate, \
             patch("songclone.orchestrator.main.get_original_audio_path") as mock_orig_path, \
             patch("songclone.orchestrator.main.get_iteration_render_path") as mock_render_path, \
             patch("songclone.orchestrator.main.save_session"):

            mock_generate_plan.return_value = mock_plan
            mock_execute_plan.return_value = "/tmp/render.wav"
            mock_evaluate.return_value = mock_evaluation
            mock_orig_path.return_value = Path(mock_session.original_audio_path)
            mock_render_path.return_value = tmp_path / "render.wav"

            await run_recreation_loop(mock_session)

            # Should only have one iteration since threshold was reached
            assert mock_generate_plan.call_count == 1
            assert mock_evaluate.call_count == 1

    @pytest.mark.asyncio
    async def test_orchestrator_stops_at_max_iterations(
        self, mock_session: Session, tmp_path: Path
    ) -> None:
        """Test that orchestrator stops when max iterations is reached."""
        mock_plan = ExecutionPlan(
            reasoning="Test plan",
            tracks=[],
            master_fx=[],
        )

        mock_evaluation = EvaluationResult(
            scores=Scores(
                timing=5, harmony=5, melody=5, instruments=5, mix=5, overall=5
            ),
            total_score=30,  # Below threshold
            max_score=60,
            feedback=[],
            stop_early=False,
            stop_reason=None,
            evaluation_method=EvaluationMethod.MFCC_FALLBACK,
        )

        with patch("songclone.orchestrator.main.generate_plan", new_callable=AsyncMock) as mock_generate_plan, \
             patch("songclone.orchestrator.main.execute_plan", new_callable=AsyncMock) as mock_execute_plan, \
             patch("songclone.orchestrator.main.evaluate_recreation", new_callable=AsyncMock) as mock_evaluate, \
             patch("songclone.orchestrator.main.get_original_audio_path") as mock_orig_path, \
             patch("songclone.orchestrator.main.get_iteration_render_path") as mock_render_path, \
             patch("songclone.orchestrator.main.save_session"):

            mock_generate_plan.return_value = mock_plan
            mock_execute_plan.return_value = "/tmp/render.wav"
            mock_evaluate.return_value = mock_evaluation
            mock_orig_path.return_value = Path(mock_session.original_audio_path)
            mock_render_path.return_value = tmp_path / "render.wav"

            await run_recreation_loop(mock_session)

            # Should have max_iterations iterations
            assert mock_generate_plan.call_count == mock_session.max_iterations
            assert mock_evaluate.call_count == mock_session.max_iterations


class TestOrchestratorLoopErrorHandling:
    """Test orchestrator error handling and recovery."""

    @pytest.mark.asyncio
    async def test_orchestrator_handles_execution_failure(
        self, mock_session: Session, tmp_path: Path
    ) -> None:
        """Test that orchestrator handles execution failures gracefully."""
        mock_plan = ExecutionPlan(
            reasoning="Test plan",
            tracks=[],
            master_fx=[],
        )

        mock_evaluation = EvaluationResult(
            scores=Scores(
                timing=9, harmony=9, melody=9, instruments=8, mix=8, overall=9
            ),
            total_score=52,
            max_score=60,
            feedback=[],
            stop_early=True,
            stop_reason="Quality threshold reached",
            evaluation_method=EvaluationMethod.AI,
        )

        with patch("songclone.orchestrator.main.generate_plan", new_callable=AsyncMock) as mock_generate_plan, \
             patch("songclone.orchestrator.main._execute_with_retries", new_callable=AsyncMock) as mock_execute, \
             patch("songclone.orchestrator.main.evaluate_recreation", new_callable=AsyncMock) as mock_evaluate, \
             patch("songclone.orchestrator.main.get_original_audio_path") as mock_orig_path, \
             patch("songclone.orchestrator.main.get_iteration_render_path") as mock_render_path, \
             patch("songclone.orchestrator.main.save_session"):

            mock_generate_plan.return_value = mock_plan
            # First execution fails, second succeeds
            mock_execute.side_effect = [None, "/tmp/render.wav"]
            mock_evaluate.return_value = mock_evaluation
            mock_orig_path.return_value = Path(mock_session.original_audio_path)
            mock_render_path.return_value = tmp_path / "render.wav"

            await run_recreation_loop(mock_session)

            # Should have attempted both iterations
            assert mock_generate_plan.call_count == 2
            # Only second iteration should reach evaluation
            assert mock_evaluate.call_count == 1
