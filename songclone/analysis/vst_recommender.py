"""VST and preset recommendation based on cached analysis results."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

AVAILABLE_VSTS = {
    "Vital": {
        "categories": ["lead", "bass", "pad", "keys", "pluck", "strings", "brass"],
        "description": "Versatile wavetable synthesizer",
    },
    "Dexed": {
        "categories": ["electric_piano", "organ", "fm_bass", "bells"],
        "description": "DX7 FM synthesizer emulation",
    },
    "ReaSynth": {
        "categories": ["simple_synth", "test_tone"],
        "description": "Simple built-in synthesizer",
    },
    "ReaSamplOmatic5000": {
        "categories": ["drums", "kit", "percussion", "samples"],
        "description": "Sample-based instrument",
    },
}

GENRE_VST_PREFERENCES = {
    "hip-hop": {
        "bass": ("Vital", "deep sub bass"),
        "other": ("Vital", "warm pad or keys"),
        "default": ("Vital", "generic"),
    },
    "lo-fi hip-hop": {
        "bass": ("Vital", "warm sub bass with saturation"),
        "other": ("Dexed", "electric piano with warmth"),
        "drums": ("ReaSamplOmatic5000", "vinyl-textured kit"),
        "default": ("Vital", "lo-fi warm"),
    },
    "electronic": {
        "bass": ("Vital", "punchy synth bass"),
        "other": ("Vital", "bright lead or pad"),
        "default": ("Vital", "electronic"),
    },
    "rock": {
        "bass": ("Vital", "distorted bass"),
        "other": ("Vital", "overdriven lead"),
        "default": ("Vital", "rock"),
    },
    "jazz": {
        "bass": ("Vital", "upright bass emulation"),
        "other": ("Dexed", "rhodes or wurlitzer"),
        "default": ("Dexed", "jazz keys"),
    },
    "pop": {
        "bass": ("Vital", "punchy pop bass"),
        "other": ("Vital", "bright synth"),
        "default": ("Vital", "pop"),
    },
    "r&b": {
        "bass": ("Vital", "smooth bass"),
        "other": ("Dexed", "neo-soul keys"),
        "default": ("Vital", "r&b"),
    },
}

INSTRUMENT_VST_MAPPING = {
    "electric_piano": {
        "vst": "Dexed",
        "preset_category": "electric_piano",
        "init_params": {"brightness": 0.6, "attack": 0.1, "decay": 0.8},
    },
    "acoustic_piano": {
        "vst": "Vital",
        "preset_category": "piano",
        "init_params": {"brightness": 0.7, "attack": 0.05, "decay": 0.9},
    },
    "synth_lead": {
        "vst": "Vital",
        "preset_category": "lead",
        "init_params": {"brightness": 0.8, "attack": 0.1, "resonance": 0.5},
    },
    "synth_pad": {
        "vst": "Vital",
        "preset_category": "pad",
        "init_params": {"attack": 0.3, "release": 0.8, "brightness": 0.5},
    },
    "synth_bass": {
        "vst": "Vital",
        "preset_category": "bass",
        "init_params": {"brightness": 0.4, "attack": 0.05, "drive": 0.3},
    },
    "acoustic_bass": {
        "vst": "Vital",
        "preset_category": "bass",
        "init_params": {"brightness": 0.3, "attack": 0.1},
    },
    "electric_bass": {
        "vst": "Vital",
        "preset_category": "bass",
        "init_params": {"brightness": 0.5, "attack": 0.05, "drive": 0.2},
    },
    "organ": {
        "vst": "Dexed",
        "preset_category": "organ",
        "init_params": {"drawbars": "888000000", "leslie": True},
    },
    "strings": {
        "vst": "Vital",
        "preset_category": "strings",
        "init_params": {"attack": 0.2, "release": 0.6},
    },
    "brass": {
        "vst": "Vital",
        "preset_category": "brass",
        "init_params": {"attack": 0.1, "brightness": 0.7},
    },
    "drums": {
        "vst": "ReaSamplOmatic5000",
        "preset_category": "kit",
        "init_params": {},
    },
    "vocals": {
        "vst": "Vital",
        "preset_category": "lead",
        "init_params": {"brightness": 0.6, "attack": 0.1},
    },
}


def recommend_vst(
    session_id: str,
    stem_name: str,
    genre_analysis: dict | None = None,
    instrument_analysis: dict | None = None,
    spectral_analysis: dict | None = None,
) -> dict[str, Any]:
    """Recommend VST and settings based on cached analysis.

    Uses genre, instrument, and spectral analysis to recommend the best
    VST plugin and initial parameters for a stem.

    Args:
        session_id: Current session ID.
        stem_name: Stem to get recommendations for (vocals, drums, bass, other).
        genre_analysis: Optional cached genre analysis result.
        instrument_analysis: Optional cached instrument analysis result.
        spectral_analysis: Optional cached spectral analysis result.

    Returns:
        dict with primary_vst, preset_category, init_params,
        fallback_vst, effects_chain, mix_suggestions.
    """
    from songclone.orchestrator.tools import get_cached_analysis

    if genre_analysis is None:
        genre_analysis = get_cached_analysis(session_id, "genre") or {}
    if instrument_analysis is None:
        instrument_analysis = get_cached_analysis(session_id, f"instrument_{stem_name}") or {}
    if spectral_analysis is None:
        spectral_analysis = get_cached_analysis(session_id, f"spectral_{stem_name}") or {}

    primary_genre = genre_analysis.get("primary_genre", "unknown")
    primary_instrument = instrument_analysis.get("primary_instrument", "unknown")
    brightness = spectral_analysis.get("brightness_category", "neutral")
    warmth = spectral_analysis.get("warmth_category", "neutral")

    if primary_instrument in INSTRUMENT_VST_MAPPING:
        vst_info = INSTRUMENT_VST_MAPPING[primary_instrument]
        primary_vst = vst_info["vst"]
        preset_category = vst_info["preset_category"]
        init_params = dict(vst_info.get("init_params", {}))
    elif primary_genre in GENRE_VST_PREFERENCES:
        genre_prefs = GENRE_VST_PREFERENCES[primary_genre]
        if stem_name in genre_prefs:
            primary_vst, preset_hint = genre_prefs[stem_name]
        else:
            primary_vst, preset_hint = genre_prefs["default"]
        preset_category = _derive_preset_category(stem_name, primary_vst)
        init_params = {}
    else:
        primary_vst = "Vital"
        preset_category = _derive_preset_category(stem_name, "Vital")
        init_params = {}

    init_params = _adjust_params_for_timbre(init_params, brightness, warmth)

    fallback_vst = _get_fallback_vst(primary_vst, stem_name)

    effects_chain = _recommend_effects_chain(
        stem_name, primary_genre, spectral_analysis, genre_analysis
    )

    mix_suggestions = _recommend_mix_settings(stem_name, spectral_analysis)

    return {
        "status": "success",
        "stem_name": stem_name,
        "primary_vst": {
            "name": primary_vst,
            "preset_category": preset_category,
            "init_params": init_params,
        },
        "fallback_vst": fallback_vst,
        "effects_chain": effects_chain,
        "mix_suggestions": mix_suggestions,
        "reasoning": _generate_reasoning(
            primary_instrument, primary_genre, primary_vst, preset_category
        ),
    }


def _derive_preset_category(stem_name: str, vst: str) -> str:
    """Derive preset category from stem name."""
    stem_category_map = {
        "vocals": "lead",
        "bass": "bass",
        "drums": "kit",
        "other": "pad",
    }
    return stem_category_map.get(stem_name, "init")


def _adjust_params_for_timbre(
    params: dict,
    brightness: str,
    warmth: str,
) -> dict:
    """Adjust VST parameters based on spectral analysis."""
    adjusted = dict(params)

    if brightness == "dark":
        adjusted["brightness"] = max(0.2, adjusted.get("brightness", 0.5) - 0.2)
        adjusted["filter_cutoff"] = adjusted.get("filter_cutoff", 0.5)
    elif brightness == "very_bright":
        adjusted["brightness"] = min(0.9, adjusted.get("brightness", 0.5) + 0.2)

    if warmth == "warm":
        adjusted["drive"] = adjusted.get("drive", 0) + 0.1
        adjusted["filter_resonance"] = max(0, adjusted.get("filter_resonance", 0.3) - 0.1)
    elif warmth == "cold":
        adjusted["drive"] = max(0, adjusted.get("drive", 0.1) - 0.05)

    return adjusted


def _get_fallback_vst(primary_vst: str, stem_name: str) -> dict:
    """Get fallback VST in case primary is unavailable."""
    if primary_vst == "Dexed":
        return {"name": "Vital", "preset_category": "keys"}
    elif primary_vst == "Vital":
        return {"name": "ReaSynth", "preset_category": "init"}
    elif primary_vst == "ReaSamplOmatic5000":
        return {"name": "ReaSynth", "preset_category": "init"}
    else:
        return {"name": "ReaSynth", "preset_category": "init"}


def _recommend_effects_chain(
    stem_name: str,
    genre: str,
    spectral: dict,
    genre_analysis: dict,
) -> list[dict]:
    """Recommend effects chain based on analysis."""
    effects = []

    brightness = spectral.get("brightness_category", "neutral")
    warmth = spectral.get("warmth_category", "neutral")
    production_style = genre_analysis.get("production_style", {})

    if stem_name in ["bass", "vocals", "other"]:
        eq_params = {}
        if brightness == "very_bright":
            eq_params["high_cut"] = 8000
        elif brightness == "dark" and stem_name != "bass":
            eq_params["high_shelf_gain"] = 2
            eq_params["high_shelf_freq"] = 5000

        if warmth == "cold" and stem_name != "drums":
            eq_params["low_shelf_gain"] = 2
            eq_params["low_shelf_freq"] = 200

        if eq_params:
            effects.append({"plugin": "ReaEQ", "params": eq_params})

    if stem_name in ["drums", "bass", "vocals"]:
        comp_params = {"ratio": 4, "attack": 10, "release": 100, "threshold": -18}

        if stem_name == "drums":
            comp_params["ratio"] = 3
            comp_params["attack"] = 5
        elif stem_name == "bass":
            comp_params["ratio"] = 4
            comp_params["attack"] = 15
        elif stem_name == "vocals":
            comp_params["ratio"] = 3
            comp_params["attack"] = 10

        effects.append({"plugin": "ReaComp", "params": comp_params})

    is_lo_fi = genre in ["lo-fi hip-hop", "indie"] or "lo-fi" in genre_analysis.get("aesthetic_tags", [])
    is_electronic = production_style.get("is_electronic", False)

    if stem_name in ["vocals", "other"]:
        verb_params = {"decay": 1.0, "wet": -15, "dry": 0}

        if is_lo_fi:
            verb_params["decay"] = 0.8
            verb_params["wet"] = -12
        elif is_electronic:
            verb_params["decay"] = 0.5
            verb_params["wet"] = -18
        else:
            verb_params["decay"] = 1.2
            verb_params["wet"] = -15

        effects.append({"plugin": "ReaVerb", "params": verb_params})

    return effects


def _recommend_mix_settings(stem_name: str, spectral: dict) -> dict:
    """Recommend mix settings based on analysis."""
    base_volumes = {
        "vocals": -3.0,
        "drums": -2.0,
        "bass": -4.0,
        "other": -6.0,
    }

    volume = base_volumes.get(stem_name, -6.0)

    brightness = spectral.get("brightness_category", "neutral")
    if brightness == "very_bright":
        volume -= 1.0
    elif brightness == "dark":
        volume += 0.5

    pan = 0.0
    if stem_name == "other":
        pan = 0.0

    return {
        "volume_db": round(volume, 1),
        "pan": pan,
    }


def _generate_reasoning(
    instrument: str,
    genre: str,
    vst: str,
    preset_category: str,
) -> str:
    """Generate human-readable reasoning for the recommendation."""
    parts = []

    if instrument != "unknown":
        parts.append(f"Detected {instrument}")
    if genre != "unknown":
        parts.append(f"in {genre} style")

    parts.append(f"→ recommending {vst} ({preset_category})")

    return " ".join(parts)
