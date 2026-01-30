"""Pydantic schemas for orchestrator agents."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TrackRole(str, Enum):
    VOCALS = "vocals"
    DRUMS = "drums"
    BASS = "bass"
    OTHER = "other"
    MASTER = "master"


class InstrumentConfig(BaseModel):
    vst: str = Field(..., description="VST plugin name, e.g., 'Vital', 'ReaSynth'")
    preset: Optional[str] = Field(None, description="Preset name")


class MidiTransform(BaseModel):
    transpose: int = Field(0, description="Semitones to transpose (positive = up)")
    velocity_scale: float = Field(1.0, ge=0, le=2, description="Velocity multiplier")


class MixSettings(BaseModel):
    volume_db: float = Field(0.0, ge=-60, le=12, description="Volume in dB (0 = unity)")
    pan: float = Field(0.0, ge=-1, le=1, description="Pan position (-1=left, 0=center, 1=right)")
    mute: bool = Field(False)


class FXConfig(BaseModel):
    plugin: str = Field(..., description="Plugin name, e.g., 'ReaEQ', 'ReaComp'")
    preset: Optional[str] = Field(None, description="Preset name")
    params: Optional[dict[str, Any]] = Field(None, description="Parameter overrides")


class TrackPlan(BaseModel):
    name: str
    role: TrackRole
    instrument: InstrumentConfig
    midi_source: str = Field(..., description="Stem name to use for MIDI, or 'generate'")
    midi_transform: Optional[MidiTransform] = None
    mix: MixSettings
    fx: list[FXConfig] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    """AI-generated recreation strategy."""

    reasoning: str = Field(..., description="Brief explanation of approach")
    tracks: list[TrackPlan]
    master_fx: list[FXConfig] = Field(default_factory=list)


class FeedbackCategory(str, Enum):
    TIMING = "timing"
    HARMONY = "harmony"
    MELODY = "melody"
    INSTRUMENTS = "instruments"
    MIX = "mix"
    OTHER = "other"


class FeedbackItem(BaseModel):
    priority: int = Field(..., ge=1, description="Priority rank (1 = highest)")
    category: FeedbackCategory
    issue: str = Field(..., description="Description of the problem")
    suggestion: str = Field(..., description="Actionable improvement suggestion")
    suggested_tools: list[str] = Field(
        default_factory=list,
        description="Analysis tools to run: analyze_genre, analyze_spectral, analyze_instrument, decompose_drums, analyze_effects, recommend_vst",
    )


class Scores(BaseModel):
    timing: int = Field(..., ge=1, le=10, description="Tempo/timing accuracy")
    harmony: int = Field(..., ge=1, le=10, description="Harmonic accuracy")
    melody: int = Field(..., ge=1, le=10, description="Melodic accuracy")
    instruments: int = Field(..., ge=1, le=10, description="Instrument selection appropriateness")
    mix: int = Field(..., ge=1, le=10, description="Mix balance quality")
    overall: int = Field(..., ge=1, le=10, description="Overall resemblance")


class EvaluationMethod(str, Enum):
    AI = "ai"
    MFCC_FALLBACK = "mfcc_fallback"


class EvaluationResult(BaseModel):
    """Quality assessment of a recreation."""

    scores: Scores
    total_score: int = Field(..., ge=0, le=60)
    max_score: int = Field(60)
    feedback: list[FeedbackItem]
    stop_early: bool = Field(False, description="True if quality is sufficient to stop")
    stop_reason: Optional[str] = Field(None, description="Reason for early stop if applicable")
    evaluation_method: EvaluationMethod
