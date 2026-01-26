"""Main orchestrator loop for iterative song recreation."""

import logging
from datetime import datetime
from pathlib import Path

from songclone.analysis.schemas import SongSpec
from songclone.api.events import (
    AudioEvent,
    CompleteEvent,
    CompleteReason,
    ErrorEvent,
    EventStatus,
    HumanActionEvent,
    IterationEvent,
    LogEvent,
    LogLevel,
    PhaseEvent,
    PhaseType,
    StepEvent,
    StepType,
    event_emitter,
)
from songclone.api.schemas import Iteration, IterationStatus, Session, SessionStatus
from songclone.api.session import (
    get_iteration_render_path,
    get_original_audio_path,
    save_session,
)
from songclone.orchestrator.agents.evaluation import evaluate_recreation
from songclone.orchestrator.agents.execution import execute_plan
from songclone.orchestrator.agents.planning import generate_plan
from songclone.orchestrator.schemas import EvaluationResult

logger = logging.getLogger(__name__)


async def run_recreation_loop(session: Session) -> None:
    """
    Run the iterative recreation loop for a session.

    Per constitution IV: Iterations follow strict plan → execute → evaluate cycle.
    Per constitution VII: Persistent file-based state enables resumption.

    Args:
        session: Session with completed analysis (song_spec populated)
    """
    if session.song_spec is None:
        await _emit_error(session.id, "Cannot start recreation: no song analysis available")
        return

    session.status = SessionStatus.ITERATING
    save_session(session)

    await event_emitter.emit(
        session.id,
        PhaseEvent(phase=PhaseType.ITERATION, status=EventStatus.STARTED),
    )

    original_path = get_original_audio_path(session.id)
    previous_evaluation: dict | None = None

    try:
        for iteration_num in range(1, session.max_iterations + 1):
            session.current_iteration = iteration_num
            save_session(session)

            await event_emitter.emit(
                session.id,
                IterationEvent(number=iteration_num, status=EventStatus.STARTED),
            )
            await _log(session.id, f"Starting iteration {iteration_num}")

            # === PLANNING STEP ===
            await event_emitter.emit(
                session.id,
                StepEvent(step=StepType.PLANNING, status=EventStatus.STARTED),
            )

            plan = await generate_plan(
                song_spec=session.song_spec,
                previous_evaluation=previous_evaluation,
                iteration=iteration_num,
            )

            iteration = Iteration(
                number=iteration_num,
                plan=plan,
                started_at=datetime.utcnow(),
                status=IterationStatus.PLANNING,
            )
            session.iterations.append(iteration)
            save_session(session)

            await event_emitter.emit(
                session.id,
                StepEvent(
                    step=StepType.PLANNING,
                    status=EventStatus.COMPLETE,
                    data={"reasoning": plan.reasoning, "track_count": len(plan.tracks)},
                ),
            )
            await _log(session.id, f"Plan generated: {len(plan.tracks)} tracks")

            # === EXECUTION STEP ===
            await event_emitter.emit(
                session.id,
                StepEvent(step=StepType.EXECUTION, status=EventStatus.STARTED),
            )

            iteration.status = IterationStatus.EXECUTING
            save_session(session)

            render_path = get_iteration_render_path(session.id, iteration_num)

            # Per constitution V: Try 3 alternative approaches before requesting human intervention
            rendered_path = await _execute_with_retries(
                session=session,
                plan=plan,
                render_path=render_path,
                iteration=iteration,
                iteration_num=iteration_num,
            )

            if rendered_path is None:
                # All retries failed, human intervention required
                continue  # Move to next iteration after human resumes

            iteration.render_path = rendered_path

            await event_emitter.emit(
                session.id,
                StepEvent(
                    step=StepType.EXECUTION,
                    status=EventStatus.COMPLETE,
                    data={"render_path": rendered_path},
                ),
            )

            await event_emitter.emit(
                session.id,
                AudioEvent(iteration=iteration_num, path=rendered_path),
            )
            await _log(session.id, f"Audio rendered: {rendered_path}")

            # === EVALUATION STEP ===
            await event_emitter.emit(
                session.id,
                StepEvent(step=StepType.EVALUATION, status=EventStatus.STARTED),
            )

            iteration.status = IterationStatus.EVALUATING
            save_session(session)

            evaluation = await evaluate_recreation(
                original_path=Path(original_path),
                recreation_path=Path(rendered_path),
                iteration=iteration_num,
                quality_threshold=session.quality_threshold,
            )

            iteration.evaluation = evaluation
            iteration.status = IterationStatus.COMPLETED
            iteration.completed_at = datetime.utcnow()
            save_session(session)

            await event_emitter.emit(
                session.id,
                StepEvent(
                    step=StepType.EVALUATION,
                    status=EventStatus.COMPLETE,
                    data={
                        "total_score": evaluation.total_score,
                        "max_score": evaluation.max_score,
                        "method": evaluation.evaluation_method.value,
                    },
                ),
            )

            await event_emitter.emit(
                session.id,
                IterationEvent(number=iteration_num, status=EventStatus.COMPLETE),
            )

            await _log(
                session.id,
                f"Iteration {iteration_num} complete: {evaluation.total_score}/{evaluation.max_score}",
            )

            # Check for early stopping
            if evaluation.stop_early:
                session.status = SessionStatus.COMPLETED
                save_session(session)

                await event_emitter.emit(
                    session.id,
                    CompleteEvent(
                        reason=CompleteReason.THRESHOLD_REACHED,
                        iterations=iteration_num,
                    ),
                )
                await _log(
                    session.id,
                    f"Quality threshold reached! Final score: {evaluation.total_score}/{evaluation.max_score}",
                )
                return

            # Store evaluation for next iteration's planning
            previous_evaluation = evaluation.model_dump()

        # Max iterations reached
        session.status = SessionStatus.COMPLETED
        save_session(session)

        await event_emitter.emit(
            session.id,
            CompleteEvent(
                reason=CompleteReason.MAX_ITERATIONS,
                iterations=session.max_iterations,
            ),
        )
        await _log(session.id, f"Max iterations ({session.max_iterations}) reached")

    except Exception as e:
        logger.exception(f"Recreation loop failed: {e}")
        session.status = SessionStatus.FAILED
        session.error = str(e)
        save_session(session)

        await _emit_error(session.id, f"Recreation loop failed: {e}", recoverable=False)

    finally:
        await event_emitter.emit(
            session.id,
            PhaseEvent(phase=PhaseType.ITERATION, status=EventStatus.COMPLETE),
        )


async def cancel_session(session: Session) -> None:
    """Cancel an in-progress session."""
    if session.status not in (SessionStatus.ANALYZING, SessionStatus.ITERATING):
        return

    session.status = SessionStatus.CANCELLED
    save_session(session)

    await event_emitter.emit(
        session.id,
        CompleteEvent(
            reason=CompleteReason.CANCELLED,
            iterations=session.current_iteration,
        ),
    )
    await _log(session.id, "Session cancelled by user", LogLevel.WARN)


async def _log(session_id: str, message: str, level: LogLevel = LogLevel.INFO) -> None:
    """Emit a log event."""
    logger.log(
        logging.INFO if level == LogLevel.INFO else logging.WARNING,
        f"[{session_id[:8]}] {message}",
    )
    await event_emitter.emit(
        session_id,
        LogEvent(level=level, message=message),
    )


async def _emit_error(session_id: str, message: str, recoverable: bool = False) -> None:
    """Emit an error event."""
    logger.error(f"[{session_id[:8]}] {message}")
    await event_emitter.emit(
        session_id,
        ErrorEvent(message=message, recoverable=recoverable),
    )


MAX_EXECUTION_RETRIES = 3


async def _execute_with_retries(
    session: Session,
    plan: "ExecutionPlan",
    render_path: Path,
    iteration: Iteration,
    iteration_num: int,
) -> str | None:
    """
    Execute plan with up to 3 retries before requesting human intervention.

    Per constitution V: Try 3 alternative approaches before human request.

    Returns:
        Rendered audio path if successful, None if all retries failed.
    """
    from songclone.orchestrator.schemas import ExecutionPlan

    last_error: Exception | None = None

    for attempt in range(1, MAX_EXECUTION_RETRIES + 1):
        try:
            await _log(
                session.id,
                f"Execution attempt {attempt}/{MAX_EXECUTION_RETRIES}",
            )

            rendered_path = await execute_plan(
                plan=plan,
                song_spec=session.song_spec,
                output_path=render_path,
            )
            return rendered_path

        except Exception as e:
            last_error = e
            logger.warning(f"Execution attempt {attempt} failed: {e}")

            if attempt < MAX_EXECUTION_RETRIES:
                await _emit_error(
                    session.id,
                    f"Execution attempt {attempt} failed: {e}. Retrying...",
                    recoverable=True,
                )
            else:
                # All retries exhausted - request human intervention
                await _request_human_intervention(
                    session=session,
                    iteration=iteration,
                    error=e,
                )
                return None

    return None


async def _request_human_intervention(
    session: Session,
    iteration: Iteration,
    error: Exception,
) -> None:
    """
    Request human intervention after all automated retries fail.

    Per constitution V: Human-in-the-loop for automation failures.
    """
    session.status = SessionStatus.PAUSED
    iteration.status = IterationStatus.FAILED
    save_session(session)

    await event_emitter.emit(
        session.id,
        HumanActionEvent(
            description="REAPER execution failed after multiple attempts",
            reason=str(error),
            steps=[
                "Open REAPER and check if it is running properly",
                "Verify that the required VST plugins are installed",
                "Check REAPER's console for error messages",
                "If needed, manually set up the project structure",
                "Click 'Resume' when ready to continue",
            ],
        ),
    )

    await _log(
        session.id,
        f"Human intervention requested: {error}",
        LogLevel.WARN,
    )
