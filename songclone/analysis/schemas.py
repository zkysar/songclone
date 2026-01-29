"""Pydantic schemas for audio analysis output."""

from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class StemRole(str, Enum):
    VOCALS = "vocals"
    DRUMS = "drums"
    BASS = "bass"
    OTHER = "other"


class VocalRange(BaseModel):
    low: str = Field(..., description="Lowest detected note, e.g., 'E3'")
    high: str = Field(..., description="Highest detected note, e.g., 'G5'")


class VocalsAnalysis(BaseModel):
    analysistype: Literal["vocals"] = "vocals"
    detected_range: VocalRange


class DrumsAnalysis(BaseModel):
    analysistype: Literal["drums"] = "drums"
    pattern_summary: str = Field(
        ...,
        description="Human-readable pattern, e.g., '4-on-floor kick, snare on 2&4'",
        alias="patternsummary",
    )

    model_config = {"populate_by_name": True}


class BassAnalysis(BaseModel):
    analysistype: Literal["bass"] = "bass"
    root_notes: list[str] = Field(..., description="Detected root notes, e.g., ['C', 'G', 'Am', 'F']")


class OtherAnalysis(BaseModel):
    analysistype: Literal["other"] = "other"
    instrument_guess: str = Field(
        ..., description="Guessed instruments, e.g., 'electric piano, synth pad'"
    )


StemAnalysis = Annotated[
    Union[VocalsAnalysis, DrumsAnalysis, BassAnalysis, OtherAnalysis],
    Field(discriminator="analysistype"),
]


class StemData(BaseModel):
    role: StemRole
    audio_path: str = Field(..., description="Path to separated WAV file")
    midi_data: str = Field(..., description="Base64-encoded MIDI file")
    analysis: Optional[StemAnalysis] = None


class Metadata(BaseModel):
    duration_seconds: float = Field(..., gt=0)
    tempo_bpm: float = Field(..., ge=20, le=300)
    time_signature: str = Field(..., pattern=r"^\d+/\d+$")
    key: str = Field(..., description="Detected key, e.g., 'C major', 'A minor'")


class Section(BaseModel):
    name: str = Field(..., description="Section type: intro, verse, chorus, bridge, outro, etc.")
    start: float = Field(..., ge=0, description="Start time in seconds")
    end: float = Field(..., ge=0, description="End time in seconds")
    bars: int = Field(..., ge=1, description="Number of bars in section")


class Structure(BaseModel):
    sections: list[Section]


class ChordEvent(BaseModel):
    time: float = Field(..., ge=0, description="Start time in seconds")
    duration: float = Field(..., gt=0, description="Duration in beats")
    chord: str = Field(..., description="Chord symbol, e.g., 'C', 'Am7', 'G/B'")


class SongSpec(BaseModel):
    """Complete analysis output for the uploaded song."""

    metadata: Metadata
    stems: dict[str, StemData] = Field(..., description="Separated stems keyed by role")
    structure: Structure
    chords: list[ChordEvent]
