"""Evaluation Agent for comparing recreations to originals."""

import json
import logging
import os
from pathlib import Path

import numpy as np

from songclone.orchestrator.schemas import (
    EvaluationMethod,
    EvaluationResult,
    FeedbackCategory,
    FeedbackItem,
    Scores,
)

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "evaluation.txt"
QUALITY_THRESHOLD = 0.8


def load_system_prompt() -> str:
    """Load the evaluation system prompt."""
    with open(PROMPT_PATH) as f:
        return f.read()


async def evaluate_recreation(
    original_path: Path,
    recreation_path: Path,
    iteration: int,
    quality_threshold: float = QUALITY_THRESHOLD,
) -> EvaluationResult:
    """
    Evaluate a recreation against the original.

    Per constitution VIII: thinking_level="high" for evaluation tasks.
    Per clarification: AI evaluation primary, MFCC fallback if AI fails.

    Args:
        original_path: Path to original audio
        recreation_path: Path to recreated audio
        iteration: Current iteration number
        quality_threshold: Score threshold for early stop (default 0.8 = 48/60)

    Returns:
        EvaluationResult with scores and feedback
    """
    try:
        result = await _ai_evaluation(original_path, recreation_path, iteration)

        threshold_score = int(quality_threshold * 60)
        if result.total_score >= threshold_score:
            result.stop_early = True
            result.stop_reason = f"Quality threshold ({quality_threshold * 100:.0f}%) reached"

        return result

    except Exception as e:
        logger.warning(f"AI evaluation failed: {e}, using MFCC fallback")
        return await _mfcc_fallback_evaluation(
            original_path, recreation_path, quality_threshold
        )


async def _ai_evaluation(
    original_path: Path,
    recreation_path: Path,
    iteration: int,
) -> EvaluationResult:
    """Evaluate using Gemini 3 Pro with audio input."""
    system_prompt = load_system_prompt()

    user_message = f"""
Compare these two audio files and evaluate how well the recreation matches the original.

This is iteration {iteration} of the recreation process.

Provide detailed scores and actionable feedback for improvement.
"""

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

        with open(original_path, "rb") as f:
            original_audio = f.read()
        with open(recreation_path, "rb") as f:
            recreation_audio = f.read()

        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=[
                types.Part.from_bytes(original_audio, mime_type="audio/wav"),
                types.Part.from_text("Original audio above. Recreation audio below:"),
                types.Part.from_bytes(recreation_audio, mime_type="audio/wav"),
                types.Part.from_text(user_message),
            ],
            config={
                "system_instruction": system_prompt,
                "thinking_config": {"thinking_level": "high"},
                "response_mime_type": "application/json",
            },
        )

        eval_data = json.loads(response.text)
        return EvaluationResult.model_validate(eval_data)

    except ImportError:
        raise RuntimeError("google-genai not available")
    except Exception as e:
        raise RuntimeError(f"AI evaluation failed: {e}")


async def _mfcc_fallback_evaluation(
    original_path: Path,
    recreation_path: Path,
    quality_threshold: float,
) -> EvaluationResult:
    """
    Fallback evaluation using MFCC spectral similarity.

    Per clarification: Automatic fallback to spectral similarity when AI fails.
    """
    logger.info("Running MFCC fallback evaluation")

    try:
        import librosa
        from scipy.spatial.distance import cosine

        y_orig, sr_orig = librosa.load(str(original_path), sr=22050)
        y_rec, sr_rec = librosa.load(str(recreation_path), sr=22050)

        min_len = min(len(y_orig), len(y_rec))
        y_orig = y_orig[:min_len]
        y_rec = y_rec[:min_len]

        mfcc_orig = librosa.feature.mfcc(y=y_orig, sr=22050, n_mfcc=13)
        mfcc_rec = librosa.feature.mfcc(y=y_rec, sr=22050, n_mfcc=13)

        mfcc_orig_mean = np.mean(mfcc_orig, axis=1)
        mfcc_rec_mean = np.mean(mfcc_rec, axis=1)

        similarity = 1 - cosine(mfcc_orig_mean, mfcc_rec_mean)
        similarity = max(0, min(1, similarity))

        base_score = int(1 + similarity * 9)

        chroma_orig = librosa.feature.chroma_cqt(y=y_orig, sr=22050)
        chroma_rec = librosa.feature.chroma_cqt(y=y_rec, sr=22050)
        chroma_sim = 1 - cosine(np.mean(chroma_orig, axis=1), np.mean(chroma_rec, axis=1))
        harmony_score = int(1 + max(0, chroma_sim) * 9)

        tempo_orig, _ = librosa.beat.beat_track(y=y_orig, sr=22050)
        tempo_rec, _ = librosa.beat.beat_track(y=y_rec, sr=22050)

        if isinstance(tempo_orig, np.ndarray):
            tempo_orig = tempo_orig[0]
        if isinstance(tempo_rec, np.ndarray):
            tempo_rec = tempo_rec[0]

        tempo_diff = abs(tempo_orig - tempo_rec) / max(tempo_orig, 1)
        timing_score = int(max(1, 10 - tempo_diff * 20))

        scores = Scores(
            timing=timing_score,
            harmony=harmony_score,
            melody=base_score,
            instruments=base_score,
            mix=base_score,
            overall=base_score,
        )

        total_score = (
            scores.timing + scores.harmony + scores.melody +
            scores.instruments + scores.mix + scores.overall
        )

        feedback = _generate_mfcc_feedback(scores, similarity)

        threshold_score = int(quality_threshold * 60)
        stop_early = total_score >= threshold_score
        stop_reason = f"Quality threshold ({quality_threshold * 100:.0f}%) reached" if stop_early else None

        return EvaluationResult(
            scores=scores,
            total_score=total_score,
            max_score=60,
            feedback=feedback,
            stop_early=stop_early,
            stop_reason=stop_reason,
            evaluation_method=EvaluationMethod.MFCC_FALLBACK,
        )

    except ImportError:
        logger.error("librosa not available for MFCC evaluation")
        return _generate_default_evaluation()
    except Exception as e:
        logger.error(f"MFCC evaluation failed: {e}")
        return _generate_default_evaluation()


def _generate_mfcc_feedback(scores: Scores, similarity: float) -> list[FeedbackItem]:
    """Generate feedback based on MFCC analysis scores."""
    feedback = []
    priority = 1

    if scores.timing < 7:
        feedback.append(FeedbackItem(
            priority=priority,
            category=FeedbackCategory.TIMING,
            issue="Tempo mismatch detected between original and recreation",
            suggestion="Verify project tempo matches the analyzed BPM",
        ))
        priority += 1

    if scores.harmony < 7:
        feedback.append(FeedbackItem(
            priority=priority,
            category=FeedbackCategory.HARMONY,
            issue="Harmonic content differs from original",
            suggestion="Check that MIDI notes are correctly transposed to match the key",
        ))
        priority += 1

    if scores.mix < 7:
        feedback.append(FeedbackItem(
            priority=priority,
            category=FeedbackCategory.MIX,
            issue="Overall spectral balance differs from original",
            suggestion="Adjust track volumes to better match the original mix",
        ))
        priority += 1

    if similarity < 0.7:
        feedback.append(FeedbackItem(
            priority=priority,
            category=FeedbackCategory.OTHER,
            issue=f"Overall similarity is low ({similarity:.1%})",
            suggestion="Review instrument selection and ensure MIDI data is complete",
        ))

    if not feedback:
        feedback.append(FeedbackItem(
            priority=1,
            category=FeedbackCategory.OTHER,
            issue="Recreation is progressing well",
            suggestion="Continue refining mix balance and instrument timbres",
        ))

    return feedback


def _generate_default_evaluation() -> EvaluationResult:
    """Generate a default evaluation when all methods fail."""
    return EvaluationResult(
        scores=Scores(
            timing=5,
            harmony=5,
            melody=5,
            instruments=5,
            mix=5,
            overall=5,
        ),
        total_score=30,
        max_score=60,
        feedback=[
            FeedbackItem(
                priority=1,
                category=FeedbackCategory.OTHER,
                issue="Evaluation unavailable",
                suggestion="Check audio files and try again",
            )
        ],
        stop_early=False,
        stop_reason=None,
        evaluation_method=EvaluationMethod.MFCC_FALLBACK,
    )
