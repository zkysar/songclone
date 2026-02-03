"""ADK tools for fetching real audio stems from Epidemic Sound.

These tools allow the orchestrator to search for and download real audio
samples instead of relying purely on VST synthesis.
"""

import logging
from pathlib import Path
from typing import Optional

from songclone.stems import get_epidemic_sound_client

logger = logging.getLogger(__name__)


def search_samples(
    query: str,
    sample_type: str = "sfx",
    limit: int = 5,
) -> dict:
    """Search Epidemic Sound for samples matching a description.

    Use this when you need a real audio sample instead of synthesized sound.
    Best for: drum hits, percussion, sound effects, one-shots.

    Args:
        query: Descriptive search (e.g., "punchy snare", "808 kick", "crisp hihat")
        sample_type: "sfx" for sound effects/one-shots, "track" for full music
        limit: Maximum results to return

    Returns:
        {
            "status": "success" or "error",
            "sample_type": "sfx" or "track",
            "matches": [
                {
                    "id": "123",
                    "title": "Punchy Snare Hit",
                    "duration_seconds": 0.5,
                    ...
                }
            ],
            "total_count": 42,
            "suggestion": "Use fetch_sample with id to download"
        }
    """
    try:
        client = get_epidemic_sound_client()

        if sample_type == "sfx":
            result = client.search_sound_effects(query=query, limit=limit)
            matches = [
                {
                    "id": m.id,
                    "title": m.title,
                    "duration_seconds": m.duration_seconds,
                    "categories": m.categories,
                }
                for m in result.matches
            ]
        else:
            result = client.search_tracks(query=query, limit=limit)
            matches = [
                {
                    "id": m.id,
                    "title": m.title,
                    "artist": m.artist,
                    "bpm": m.bpm,
                    "duration_seconds": m.duration_seconds,
                    "genres": m.genres,
                    "moods": m.moods,
                    "stems_available": m.stems_available,
                }
                for m in result.matches
            ]

        return {
            "status": "success",
            "sample_type": sample_type,
            "query": query,
            "matches": matches,
            "total_count": result.total_count,
            "suggestion": "Use fetch_sample with the id to download the audio file",
        }

    except Exception as e:
        logger.error(f"Sample search failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "suggestion": "Check EPIDEMIC_SOUND_API_KEY is set correctly",
        }


def search_similar_tracks(
    reference_track_id: str,
    limit: int = 5,
) -> dict:
    """Find tracks similar to a reference track.

    Use after finding a good track to discover alternatives.

    Args:
        reference_track_id: Epidemic Sound track ID to find similar tracks for
        limit: Maximum results

    Returns:
        Similar format to search_samples with track matches
    """
    try:
        client = get_epidemic_sound_client()
        result = client.find_similar_tracks(track_id=reference_track_id, limit=limit)

        matches = [
            {
                "id": m.id,
                "title": m.title,
                "artist": m.artist,
                "bpm": m.bpm,
                "duration_seconds": m.duration_seconds,
                "genres": m.genres,
                "moods": m.moods,
                "stems_available": m.stems_available,
            }
            for m in result.matches
        ]

        return {
            "status": "success",
            "reference_id": reference_track_id,
            "matches": matches,
            "total_count": result.total_count,
        }

    except Exception as e:
        logger.error(f"Similar track search failed: {e}")
        return {"status": "error", "error": str(e)}


def fetch_sample(
    sample_id: str,
    sample_type: str = "sfx",
    output_dir: Optional[str] = None,
) -> dict:
    """Download a sample from Epidemic Sound.

    Downloads the audio file locally so it can be used in REAPER.

    Args:
        sample_id: The Epidemic Sound asset ID from search results
        sample_type: "sfx" for sound effects, "track" for full tracks
        output_dir: Optional directory to save to. Uses cache if not specified.

    Returns:
        {
            "status": "success" or "error",
            "local_path": "/path/to/downloaded/file.mp3",
            "asset_id": "123",
            "asset_type": "sfx" or "track"
        }
    """
    try:
        client = get_epidemic_sound_client()
        output_path = Path(output_dir) / f"{sample_type}_{sample_id}.wav" if output_dir else None

        if sample_type == "sfx":
            result = client.download_sfx(
                sfx_id=sample_id,
                output_path=output_path,
            )
        else:
            result = client.download_track(
                track_id=sample_id,
                output_path=output_path,
            )

        if result.success:
            return {
                "status": "success",
                "local_path": result.local_path,
                "asset_id": result.asset_id,
                "asset_type": result.asset_type,
                "format": result.format.value,
            }
        else:
            return {
                "status": "error",
                "error": result.error,
                "asset_id": sample_id,
            }

    except Exception as e:
        logger.error(f"Sample fetch failed: {e}")
        return {"status": "error", "error": str(e)}


def search_drum_samples(
    drum_type: str,
    style: Optional[str] = None,
    limit: int = 5,
) -> dict:
    """Specialized search for drum samples.

    Convenience wrapper for common drum sample searches.

    Args:
        drum_type: One of "kick", "snare", "hihat", "tom", "cymbal", "clap", "percussion"
        style: Optional style modifier (e.g., "punchy", "808", "acoustic", "electronic")
        limit: Maximum results

    Returns:
        Search results with matching drum samples
    """
    style_terms = {
        "kick": ["kick drum", "bass drum"],
        "snare": ["snare drum", "snare hit"],
        "hihat": ["hi-hat", "hihat", "hi hat"],
        "tom": ["tom drum", "floor tom"],
        "cymbal": ["cymbal", "crash", "ride"],
        "clap": ["clap", "handclap"],
        "percussion": ["percussion", "perc hit"],
    }

    base_terms = style_terms.get(drum_type.lower(), [drum_type])
    query = f"{style} {base_terms[0]}" if style else base_terms[0]

    return search_samples(query=query, sample_type="sfx", limit=limit)


def search_instrument_samples(
    instrument: str,
    genre: Optional[str] = None,
    mood: Optional[str] = None,
    bpm: Optional[int] = None,
    limit: int = 5,
) -> dict:
    """Search for instrument loops or stems.

    Args:
        instrument: Instrument type (e.g., "bass", "guitar", "piano", "synth")
        genre: Optional genre filter
        mood: Optional mood filter
        bpm: Optional tempo to match
        limit: Maximum results

    Returns:
        Search results with matching tracks that have stems
    """
    try:
        client = get_epidemic_sound_client()

        query = instrument
        if genre:
            query = f"{genre} {instrument}"

        genres_filter = [genre] if genre else None
        moods_filter = [mood] if mood else None

        result = client.search_tracks(
            query=query,
            genres=genres_filter,
            moods=moods_filter,
            bpm_min=bpm - 5 if bpm else None,
            bpm_max=bpm + 5 if bpm else None,
            limit=limit,
        )

        matches = [
            {
                "id": m.id,
                "title": m.title,
                "artist": m.artist,
                "bpm": m.bpm,
                "duration_seconds": m.duration_seconds,
                "genres": m.genres,
                "moods": m.moods,
                "stems_available": m.stems_available,
                "has_requested_stem": instrument.lower() in [s.lower() for s in m.stems_available],
            }
            for m in result.matches
        ]

        return {
            "status": "success",
            "instrument": instrument,
            "matches": matches,
            "total_count": result.total_count,
            "suggestion": "Tracks with has_requested_stem=True have the instrument as a separate stem",
        }

    except Exception as e:
        logger.error(f"Instrument search failed: {e}")
        return {"status": "error", "error": str(e)}
