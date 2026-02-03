"""Pydantic schemas for Epidemic Sound stems/samples integration."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AudioFormat(str, Enum):
    MP3 = "mp3"
    WAV = "wav"


class AudioQuality(str, Enum):
    NORMAL = "normal"  # 128kbps
    HIGH = "high"  # 320kbps


class SampleMatch(BaseModel):
    """A matching sound effect from Epidemic Sound."""

    id: str = Field(..., description="Epidemic Sound SFX ID")
    title: str
    duration_seconds: float
    categories: list[str] = Field(default_factory=list)
    preview_url: Optional[str] = None


class SampleSearchResult(BaseModel):
    """Result of searching for sound effects."""

    query: str
    matches: list[SampleMatch]
    total_count: int
    has_more: bool = False


class TrackMatch(BaseModel):
    """A matching music track from Epidemic Sound."""

    id: str = Field(..., description="Epidemic Sound track ID")
    title: str
    artist: str
    bpm: Optional[int] = None
    duration_seconds: float
    genres: list[str] = Field(default_factory=list)
    moods: list[str] = Field(default_factory=list)
    energy_level: Optional[str] = None
    has_vocals: bool = False
    preview_url: Optional[str] = None
    stems_available: list[str] = Field(
        default_factory=list,
        description="Available stem types: drums, bass, melody, vocals, etc.",
    )


class TrackSearchResult(BaseModel):
    """Result of searching for music tracks."""

    query: str
    filters: dict = Field(default_factory=dict)
    matches: list[TrackMatch]
    total_count: int
    has_more: bool = False


class StemDownloadResult(BaseModel):
    """Result of downloading a stem or sample."""

    success: bool
    asset_id: str
    asset_type: str = Field(..., description="'track', 'stem', or 'sfx'")
    stem_name: Optional[str] = Field(None, description="Stem type if downloading from track")
    local_path: str = Field(default="", description="Path where audio was saved")
    download_url: Optional[str] = Field(None, description="CDN URL if not saving locally")
    format: AudioFormat = AudioFormat.MP3
    quality: AudioQuality = AudioQuality.HIGH
    expires_in_hours: int = Field(default=1, description="How long the download URL is valid")
    error: Optional[str] = None
