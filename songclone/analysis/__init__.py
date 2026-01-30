"""Audio analysis pipeline for stem separation, MIDI extraction, and feature detection."""

from songclone.analysis.drum_decomposer import decompose_drums
from songclone.analysis.effects_analyzer import analyze_effects
from songclone.analysis.genre_detector import analyze_genre
from songclone.analysis.instrument_classifier import analyze_instrument
from songclone.analysis.spectral_extractor import analyze_spectral
from songclone.analysis.vst_recommender import recommend_vst

__all__ = [
    "analyze_genre",
    "analyze_instrument",
    "analyze_spectral",
    "decompose_drums",
    "analyze_effects",
    "recommend_vst",
]
