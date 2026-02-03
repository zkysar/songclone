"""Epidemic Sound MCP client for fetching stems and samples.

Uses the Epidemic Sound MCP Server via Streamable HTTP transport.
Server: https://www.epidemicsound.com/a/mcp-service/mcp
Docs: https://developers.epidemicsite.com/docs/mcp/
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from songclone.stems.schemas import (
    AudioFormat,
    AudioQuality,
    SampleMatch,
    SampleSearchResult,
    StemDownloadResult,
    TrackMatch,
    TrackSearchResult,
)

logger = logging.getLogger(__name__)

MCP_URL = "https://www.epidemicsound.com/a/mcp-service/mcp"
DOWNLOAD_TIMEOUT = 120.0


class EpidemicSoundClient:
    """Client for Epidemic Sound MCP Server.

    Available stem types for downloads: FULL, BASS, DRUMS, INSTRUMENTS
    """

    def __init__(self, api_key: Optional[str] = None, cache_dir: Optional[Path] = None):
        self.api_key = api_key or os.environ.get("EPIDEMIC_SOUND_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Epidemic Sound API key required. Set EPIDEMIC_SOUND_API_KEY "
                "environment variable or pass api_key parameter."
            )

        self.cache_dir = cache_dir or Path.home() / ".cache" / "songclone" / "stems"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call an MCP tool on the Epidemic Sound server."""
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)

                if result.isError:
                    error_text = "".join(
                        c.text for c in result.content if hasattr(c, "text")
                    )
                    return {"error": error_text}

                for content in result.content:
                    if hasattr(content, "text"):
                        try:
                            return json.loads(content.text)
                        except json.JSONDecodeError:
                            return {"text": content.text}

                return {"error": "No content in response"}

    def _run_async(self, coro):
        """Run async code from sync context."""
        try:
            asyncio.get_running_loop()
            import nest_asyncio
            nest_asyncio.apply()
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    def search_tracks(
        self,
        query: str,
        genres: Optional[list[str]] = None,
        moods: Optional[list[str]] = None,
        instruments: Optional[list[str]] = None,
        bpm_min: Optional[int] = None,
        bpm_max: Optional[int] = None,
        has_vocals: Optional[bool] = None,
        key: Optional[str] = None,
        limit: int = 10,
    ) -> TrackSearchResult:
        """Search for music tracks (recordings).

        Args:
            query: Search keywords
            genres: Genre slugs (e.g., ["rock", "pop"])
            moods: Mood slugs
            instruments: Instrument slugs (e.g., ["acoustic-guitar"])
            bpm_min: Minimum BPM
            bpm_max: Maximum BPM
            has_vocals: Filter for tracks with/without vocals
            key: Musical key (e.g., "c-minor")
            limit: Max results
        """
        args: dict[str, Any] = {
            "query": {"term": query},
            "first": limit,
        }
        filters: dict[str, Any] = {"query": query}
        recording_filter: dict[str, Any] = {}

        if bpm_min or bpm_max:
            bpm_filter: dict[str, Any] = {}
            if bpm_min:
                bpm_filter["min"] = bpm_min
                filters["bpm_min"] = bpm_min
            if bpm_max:
                bpm_filter["max"] = bpm_max
                filters["bpm_max"] = bpm_max
            recording_filter["bpm"] = bpm_filter

        if genres:
            recording_filter["taxonomySlugs"] = {"matchType": "ANY", "values": genres}
            filters["genres"] = genres
        if moods:
            recording_filter["moodSlugs"] = {"matchType": "ANY", "values": moods}
            filters["moods"] = moods
        if instruments:
            recording_filter["featuredInstrumentSlugs"] = {"matchType": "ANY", "values": instruments}
            filters["instruments"] = instruments
        if has_vocals is not None:
            recording_filter["vocals"] = has_vocals
            filters["has_vocals"] = has_vocals
        if key:
            recording_filter["musicalKeys"] = [key]
            filters["key"] = key

        if recording_filter:
            args["filter"] = recording_filter

        try:
            result = self._run_async(self._call_tool("SearchRecordings", args))
        except Exception as e:
            logger.error(f"Track search failed: {e}")
            return TrackSearchResult(query=query, filters=filters, matches=[], total_count=0)

        if "error" in result:
            logger.error(f"Track search error: {result['error']}")
            return TrackSearchResult(query=query, filters=filters, matches=[], total_count=0)

        nodes = result.get("data", {}).get("recordings", {}).get("nodes", [])
        matches = []
        for node in nodes:
            rec = node.get("recording", {})
            artists = rec.get("artists", [])
            artist_name = artists[0].get("name", "Unknown") if artists else "Unknown"

            matches.append(
                TrackMatch(
                    id=rec.get("id", ""),
                    title=rec.get("title", "Unknown"),
                    artist=artist_name,
                    bpm=rec.get("bpm"),
                    duration_seconds=(rec.get("audioFile", {}).get("durationInMilliseconds", 0)) / 1000,
                    genres=[t.get("displayName", "") for t in rec.get("taxonomies", [])],
                    moods=[m.get("displayName", "") for m in rec.get("moods", [])],
                    energy_level=rec.get("energyLevel"),
                    has_vocals=rec.get("hasVocals", False),
                    stems_available=["FULL", "BASS", "DRUMS", "INSTRUMENTS"],
                )
            )

        return TrackSearchResult(
            query=query,
            filters=filters,
            matches=matches,
            total_count=len(matches),
        )

    def search_sound_effects(
        self,
        query: str,
        duration_max_ms: Optional[int] = None,
        tags: Optional[list[str]] = None,
        limit: int = 10,
    ) -> SampleSearchResult:
        """Search for sound effects.

        Args:
            query: Search keywords (e.g., "snare drum", "kick 808")
            duration_max_ms: Max duration in milliseconds
            tags: Tag slugs to filter by
            limit: Max results
        """
        args: dict[str, Any] = {
            "query": {"term": query},
            "first": limit,
        }

        sfx_filter: dict[str, Any] = {}
        if duration_max_ms:
            sfx_filter["duration"] = {"max": duration_max_ms}
        if tags:
            sfx_filter["tagSlugs"] = {"matchType": "ANY", "values": tags}
        if sfx_filter:
            args["filter"] = sfx_filter

        try:
            result = self._run_async(self._call_tool("SearchSoundEffects", args))
        except Exception as e:
            logger.error(f"SFX search failed: {e}")
            return SampleSearchResult(query=query, matches=[], total_count=0)

        if "error" in result:
            logger.error(f"SFX search error: {result['error']}")
            return SampleSearchResult(query=query, matches=[], total_count=0)

        nodes = result.get("data", {}).get("soundEffects", {}).get("nodes", [])
        matches = []
        for node in nodes:
            sfx = node.get("soundEffect", {})
            audio = sfx.get("audioFile", {})
            matches.append(
                SampleMatch(
                    id=sfx.get("id", ""),
                    title=sfx.get("title", "Unknown"),
                    duration_seconds=audio.get("durationInMilliseconds", 0) / 1000,
                    categories=[t.get("displayName", "") for t in sfx.get("tags", [])],
                    preview_url=audio.get("lqmp3Url"),
                )
            )

        return SampleSearchResult(
            query=query,
            matches=matches,
            total_count=len(matches),
        )

    def find_similar_tracks(self, track_id: str, limit: int = 5) -> TrackSearchResult:
        """Find tracks similar to a given track."""
        try:
            result = self._run_async(
                self._call_tool("SearchSimilarToRecording", {"id": track_id, "first": limit})
            )
        except Exception as e:
            logger.error(f"Similar search failed: {e}")
            return TrackSearchResult(
                query=f"similar:{track_id}", filters={}, matches=[], total_count=0
            )

        if "error" in result:
            return TrackSearchResult(
                query=f"similar:{track_id}", filters={}, matches=[], total_count=0
            )

        nodes = result.get("data", {}).get("recordings", {}).get("nodes", [])
        matches = []
        for node in nodes:
            rec = node.get("recording", {})
            artists = rec.get("artists", [])
            matches.append(
                TrackMatch(
                    id=rec.get("id", ""),
                    title=rec.get("title", "Unknown"),
                    artist=artists[0].get("name", "Unknown") if artists else "Unknown",
                    bpm=rec.get("bpm"),
                    duration_seconds=(rec.get("audioFile", {}).get("durationInMilliseconds", 0)) / 1000,
                    genres=[t.get("displayName", "") for t in rec.get("taxonomies", [])],
                    moods=[m.get("displayName", "") for m in rec.get("moods", [])],
                    stems_available=["FULL", "BASS", "DRUMS", "INSTRUMENTS"],
                )
            )

        return TrackSearchResult(
            query=f"similar:{track_id}",
            filters={"reference_id": track_id},
            matches=matches,
            total_count=len(matches),
        )

    def download_track(
        self,
        track_id: str,
        stem: str = "FULL",
        file_type: str = "WAV",
        output_path: Optional[Path] = None,
    ) -> StemDownloadResult:
        """Download a track or specific stem.

        Args:
            track_id: Epidemic Sound recording UUID
            stem: One of "FULL", "BASS", "DRUMS", "INSTRUMENTS"
            file_type: "WAV" or "MP3"
            output_path: Where to save. Defaults to cache directory.
        """
        ext = file_type.lower()
        stem_suffix = f"_{stem.lower()}" if stem != "FULL" else ""
        filename = f"track_{track_id}{stem_suffix}.{ext}"

        if output_path is None:
            output_path = self.cache_dir / filename
        else:
            output_path = Path(output_path)

        if output_path.exists():
            logger.info(f"Using cached: {output_path}")
            return StemDownloadResult(
                success=True,
                asset_id=track_id,
                asset_type="stem" if stem != "FULL" else "track",
                stem_name=stem if stem != "FULL" else None,
                local_path=str(output_path),
                format=AudioFormat.WAV if file_type == "WAV" else AudioFormat.MP3,
                quality=AudioQuality.HIGH,
            )

        try:
            result = self._run_async(self._call_tool("DownloadRecording", {
                "id": track_id,
                "options": {"fileType": file_type, "stemType": stem},
            }))
        except Exception as e:
            return StemDownloadResult(
                success=False, asset_id=track_id, asset_type="track",
                error=str(e), format=AudioFormat.WAV,
            )

        if "error" in result:
            return StemDownloadResult(
                success=False, asset_id=track_id, asset_type="track",
                error=result["error"], format=AudioFormat.WAV,
            )

        data = result.get("data", {})
        download_url = (
            data.get("recordingDownload", {}).get("assetUrl")
            or data.get("download", {}).get("assetUrl")
            or result.get("assetUrl")
        )
        if not download_url:
            return StemDownloadResult(
                success=False, asset_id=track_id, asset_type="track",
                error=f"No download URL in response: {json.dumps(result)[:200]}",
                format=AudioFormat.WAV,
            )

        try:
            response = httpx.get(download_url, timeout=DOWNLOAD_TIMEOUT, follow_redirects=True)
            response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.content)
            logger.info(f"Downloaded to: {output_path}")

            return StemDownloadResult(
                success=True,
                asset_id=track_id,
                asset_type="stem" if stem != "FULL" else "track",
                stem_name=stem if stem != "FULL" else None,
                local_path=str(output_path),
                format=AudioFormat.WAV if file_type == "WAV" else AudioFormat.MP3,
                quality=AudioQuality.HIGH,
            )
        except Exception as e:
            return StemDownloadResult(
                success=False, asset_id=track_id, asset_type="track",
                error=str(e), format=AudioFormat.WAV,
            )

    def download_sfx(
        self,
        sfx_id: str,
        file_type: str = "WAV",
        output_path: Optional[Path] = None,
    ) -> StemDownloadResult:
        """Download a sound effect.

        Args:
            sfx_id: Epidemic Sound SFX UUID
            file_type: "WAV" or "MP3"
            output_path: Where to save. Defaults to cache directory.
        """
        ext = file_type.lower()
        filename = f"sfx_{sfx_id}.{ext}"

        if output_path is None:
            output_path = self.cache_dir / filename
        else:
            output_path = Path(output_path)

        if output_path.exists():
            logger.info(f"Using cached: {output_path}")
            return StemDownloadResult(
                success=True, asset_id=sfx_id, asset_type="sfx",
                local_path=str(output_path),
                format=AudioFormat.WAV if file_type == "WAV" else AudioFormat.MP3,
                quality=AudioQuality.HIGH,
            )

        try:
            result = self._run_async(self._call_tool("DownloadSoundEffect", {
                "id": sfx_id,
                "options": {"fileType": file_type},
            }))
        except Exception as e:
            return StemDownloadResult(
                success=False, asset_id=sfx_id, asset_type="sfx",
                error=str(e), format=AudioFormat.WAV,
            )

        if "error" in result:
            return StemDownloadResult(
                success=False, asset_id=sfx_id, asset_type="sfx",
                error=result["error"], format=AudioFormat.WAV,
            )

        data = result.get("data", {})
        download_url = (
            data.get("soundEffectDownload", {}).get("assetUrl")
            or data.get("download", {}).get("assetUrl")
            or result.get("assetUrl")
        )
        if not download_url:
            return StemDownloadResult(
                success=False, asset_id=sfx_id, asset_type="sfx",
                error="No download URL in response", format=AudioFormat.WAV,
            )

        try:
            response = httpx.get(download_url, timeout=DOWNLOAD_TIMEOUT, follow_redirects=True)
            response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.content)
            logger.info(f"Downloaded SFX to: {output_path}")

            return StemDownloadResult(
                success=True, asset_id=sfx_id, asset_type="sfx",
                local_path=str(output_path),
                format=AudioFormat.WAV if file_type == "WAV" else AudioFormat.MP3,
                quality=AudioQuality.HIGH,
            )
        except Exception as e:
            return StemDownloadResult(
                success=False, asset_id=sfx_id, asset_type="sfx",
                error=str(e), format=AudioFormat.WAV,
            )

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


_client_instance: Optional[EpidemicSoundClient] = None


def get_epidemic_sound_client() -> EpidemicSoundClient:
    """Get or create the singleton Epidemic Sound client."""
    global _client_instance
    if _client_instance is None:
        _client_instance = EpidemicSoundClient()
    return _client_instance
