"""Stems module for fetching real audio samples from Epidemic Sound."""

from songclone.stems.epidemic_sound import EpidemicSoundClient, get_epidemic_sound_client
from songclone.stems.schemas import (
    AudioFormat,
    SampleMatch,
    SampleSearchResult,
    StemDownloadResult,
    TrackMatch,
    TrackSearchResult,
)

__all__ = [
    "AudioFormat",
    "EpidemicSoundClient",
    "SampleMatch",
    "SampleSearchResult",
    "StemDownloadResult",
    "TrackMatch",
    "TrackSearchResult",
    "get_epidemic_sound_client",
]
