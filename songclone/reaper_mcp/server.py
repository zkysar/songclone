"""MCP server for REAPER DAW batch operations."""

import asyncio
import json
import logging
import sys
from typing import Any

from songclone.reaper_mcp.tools import (
    BatchCreateTracksInput,
    BatchInsertMidiInput,
    BatchSetFXInput,
    BatchSetLevelsInput,
    CreateProjectInput,
    FXConfig,
    FXItem,
    LevelConfig,
    MidiInsertItem,
    RenderAudioInput,
    TrackConfig,
    batch_create_tracks,
    batch_insert_midi,
    batch_set_fx,
    batch_set_levels,
    create_project,
    get_project_state,
    render_audio,
)

logger = logging.getLogger(__name__)


class ReaperMCPServer:
    """
    MCP server providing batch operations for REAPER DAW.

    Per constitution III:
    - Batch operations preferred over individual calls
    - Every tool returns a typed response
    - Tools are idempotent where possible
    - REAPER state verified after batch operations
    """

    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {
            "create_project": {
                "description": "Initialize a new REAPER project with tempo and time signature",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tempo": {"type": "number", "minimum": 20, "maximum": 300},
                        "time_signature": {"type": "string", "pattern": "^\\d+/\\d+$"},
                        "duration_seconds": {"type": "number", "minimum": 1},
                    },
                    "required": ["tempo", "time_signature", "duration_seconds"],
                },
                "handler": self._handle_create_project,
            },
            "batch_create_tracks": {
                "description": "Create multiple tracks with instruments in one call",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tracks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "instrument_vst": {"type": "string"},
                                    "instrument_preset": {"type": "string"},
                                    "color": {"type": "string"},
                                },
                                "required": ["name", "instrument_vst"],
                            },
                        },
                    },
                    "required": ["tracks"],
                },
                "handler": self._handle_batch_create_tracks,
            },
            "batch_insert_midi": {
                "description": "Insert MIDI data into multiple tracks",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "track_id": {"type": "string"},
                                    "midi_data": {"type": "string"},
                                    "start_time": {"type": "number"},
                                    "velocity_scale": {"type": "number"},
                                },
                                "required": ["track_id", "midi_data"],
                            },
                        },
                    },
                    "required": ["items"],
                },
                "handler": self._handle_batch_insert_midi,
            },
            "batch_set_fx": {
                "description": "Add/configure FX chains on multiple tracks",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "fx_configs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "track_id": {"type": "string"},
                                    "fx_chain": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "plugin": {"type": "string"},
                                                "preset": {"type": "string"},
                                                "params": {"type": "object"},
                                            },
                                            "required": ["plugin"],
                                        },
                                    },
                                },
                                "required": ["track_id", "fx_chain"],
                            },
                        },
                    },
                    "required": ["fx_configs"],
                },
                "handler": self._handle_batch_set_fx,
            },
            "batch_set_levels": {
                "description": "Set volume, pan, mute for multiple tracks",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "levels": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "track_id": {"type": "string"},
                                    "volume_db": {"type": "number"},
                                    "pan": {"type": "number"},
                                    "mute": {"type": "boolean"},
                                },
                                "required": ["track_id"],
                            },
                        },
                    },
                    "required": ["levels"],
                },
                "handler": self._handle_batch_set_levels,
            },
            "render_audio": {
                "description": "Render project to audio file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "output_path": {"type": "string"},
                        "format": {"type": "string", "default": "wav"},
                        "start_time": {"type": "number"},
                        "end_time": {"type": "number"},
                    },
                    "required": ["output_path"],
                },
                "handler": self._handle_render_audio,
            },
            "get_project_state": {
                "description": "Get current state of all tracks for verification",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
                "handler": self._handle_get_project_state,
            },
        }

    async def _handle_create_project(self, params: dict[str, Any]) -> dict[str, Any]:
        """Create a new REAPER project with tempo and time signature."""
        input_data = CreateProjectInput(
            tempo=params["tempo"],
            time_signature=params["time_signature"],
            duration_seconds=params["duration_seconds"],
        )
        result = await create_project(input_data)
        return result.model_dump()

    async def _handle_batch_create_tracks(self, params: dict[str, Any]) -> dict[str, Any]:
        """Create multiple tracks with instruments."""
        tracks = [
            TrackConfig(
                name=t["name"],
                instrument_vst=t["instrument_vst"],
                instrument_preset=t.get("instrument_preset"),
                color=t.get("color"),
            )
            for t in params["tracks"]
        ]
        input_data = BatchCreateTracksInput(tracks=tracks)
        result = await batch_create_tracks(input_data)
        return result.model_dump()

    async def _handle_batch_insert_midi(self, params: dict[str, Any]) -> dict[str, Any]:
        """Insert MIDI data into multiple tracks."""
        items = [
            MidiInsertItem(
                track_id=i["track_id"],
                midi_data=i["midi_data"],
                start_time=i.get("start_time", 0),
                velocity_scale=i.get("velocity_scale", 1.0),
            )
            for i in params["items"]
        ]
        input_data = BatchInsertMidiInput(items=items)
        result = await batch_insert_midi(input_data)
        return result.model_dump()

    async def _handle_batch_set_fx(self, params: dict[str, Any]) -> dict[str, Any]:
        """Add/configure FX chains on multiple tracks."""
        fx_configs = [
            FXConfig(
                track_id=cfg["track_id"],
                fx_chain=[
                    FXItem(
                        plugin=fx["plugin"],
                        preset=fx.get("preset"),
                        params=fx.get("params"),
                    )
                    for fx in cfg["fx_chain"]
                ],
            )
            for cfg in params["fx_configs"]
        ]
        input_data = BatchSetFXInput(fx_configs=fx_configs)
        result = await batch_set_fx(input_data)
        return result.model_dump()

    async def _handle_batch_set_levels(self, params: dict[str, Any]) -> dict[str, Any]:
        """Set volume, pan, mute for multiple tracks."""
        levels = [
            LevelConfig(
                track_id=lvl["track_id"],
                volume_db=lvl.get("volume_db"),
                pan=lvl.get("pan"),
                mute=lvl.get("mute"),
            )
            for lvl in params["levels"]
        ]
        input_data = BatchSetLevelsInput(levels=levels)
        result = await batch_set_levels(input_data)
        return result.model_dump()

    async def _handle_render_audio(self, params: dict[str, Any]) -> dict[str, Any]:
        """Render project to audio file."""
        input_data = RenderAudioInput(
            output_path=params["output_path"],
            format=params.get("format", "wav"),
            start_time=params.get("start_time"),
            end_time=params.get("end_time"),
        )
        result = await render_audio(input_data)
        return result.model_dump()

    async def _handle_get_project_state(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get current state of all tracks for verification."""
        result = await get_project_state()
        return result.model_dump()

    async def handle_tool_call(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle an MCP tool call."""
        if tool_name not in self.tools:
            return {"error": f"Unknown tool: {tool_name}"}

        handler = self.tools[tool_name]["handler"]
        return await handler(params)

    def list_tools(self) -> list[dict[str, Any]]:
        """List available tools with their schemas."""
        return [
            {
                "name": name,
                "description": info["description"],
                "inputSchema": info.get("inputSchema", {}),
            }
            for name, info in self.tools.items()
        ]

    async def run_stdio(self) -> None:
        """Run the MCP server using stdio transport."""
        logger.info("REAPER MCP server starting (stdio transport)...")

        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )

                if not line:
                    break

                request = json.loads(line)
                method = request.get("method", "")
                request_id = request.get("id")

                if method == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"tools": self.list_tools()},
                    }
                elif method == "tools/call":
                    tool_name = request.get("params", {}).get("name")
                    tool_args = request.get("params", {}).get("arguments", {})
                    result = await self.handle_tool_call(tool_name, tool_args)
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result)}]},
                    }
                elif method == "initialize":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {
                                "name": "reaper-mcp",
                                "version": "1.0.0",
                            },
                        },
                    }
                else:
                    # Legacy format support
                    tool_name = request.get("tool")
                    params = request.get("params", {})
                    if tool_name:
                        result = await self.handle_tool_call(tool_name, params)
                        response = result
                    else:
                        response = {"error": f"Unknown method: {method}"}

                print(json.dumps(response), flush=True)

            except json.JSONDecodeError as e:
                error_response = json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {e}"},
                })
                print(error_response, flush=True)
            except Exception as e:
                logger.exception("Error handling request")
                error_response = json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(e)},
                })
                print(error_response, flush=True)


def main() -> None:
    """Entry point for the MCP server."""
    logging.basicConfig(level=logging.INFO)
    server = ReaperMCPServer()
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
