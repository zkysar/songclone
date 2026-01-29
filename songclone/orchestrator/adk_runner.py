"""ADK Runner integration for FastAPI.

This module provides ADK Runner integration that can be used by the FastAPI app
to run the orchestrator agent with proper session management and event streaming.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import AsyncGenerator

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from songclone.analysis.schemas import SongSpec
from songclone.orchestrator.agent import root_agent
from songclone.orchestrator.langfuse_config import (
    init_langfuse,
    print_trace_link,
    start_trace,
)
from songclone.orchestrator.tools import init_midi_store

logger = logging.getLogger(__name__)

# Initialize Langfuse at module load
_langfuse_enabled = init_langfuse()

APP_NAME = "songclone"

# Shared session service - initialized once at app startup
_session_service: InMemorySessionService | None = None
_runner: Runner | None = None


def get_session_service() -> InMemorySessionService:
    """Get or create the shared session service."""
    global _session_service
    if _session_service is None:
        _session_service = InMemorySessionService()
        logger.info("ADK InMemorySessionService initialized")
    return _session_service


def get_runner() -> Runner:
    """Get or create the shared ADK runner."""
    global _runner
    if _runner is None:
        _runner = Runner(
            agent=root_agent,
            app_name=APP_NAME,
            session_service=get_session_service(),
        )
        logger.info(f"ADK Runner initialized for agent: {root_agent.name}")
    return _runner


async def create_adk_session(session_id: str, user_id: str = "user") -> None:
    """Create an ADK session for a recreation workflow."""
    service = get_session_service()
    await service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    logger.info(f"ADK session created: {session_id}")


async def run_orchestrator_with_adk(
    session_id: str,
    song_spec_json: str,
    original_audio_path: str,
    output_dir: str,
    max_iterations: int = 10,
    quality_threshold: float = 0.8,
    user_id: str = "user",
) -> AsyncGenerator[dict, None]:
    """
    Run the orchestrator using ADK Runner.

    Yields events as they occur for SSE streaming.

    Args:
        session_id: Unique session identifier
        song_spec_json: JSON string of the song analysis
        original_audio_path: Path to original audio file
        output_dir: Directory for rendered outputs
        max_iterations: Maximum iteration count
        quality_threshold: Score threshold (0-1) to stop early
        user_id: User identifier for ADK session

    Yields:
        Event dictionaries with type and data
    """
    print(f"=== run_orchestrator_with_adk ENTERED ===", flush=True)

    # Emit initial status
    yield {
        "type": "log",
        "message": "Starting orchestrator agent...",
    }

    runner = get_runner()
    print(f"=== Got ADK runner ===", flush=True)

    # Ensure session exists
    try:
        await create_adk_session(session_id, user_id)
        print(f"=== ADK session ensured ===", flush=True)
    except Exception:
        # Session might already exist
        print(f"=== ADK session already exists ===", flush=True)
        pass

    yield {
        "type": "log",
        "message": "Orchestrator ready. Sending song analysis to AI agent...",
    }

    # Parse and initialize MIDI store
    print(f"=== Parsing song_spec and initializing MIDI store ===", flush=True)
    try:
        song_spec = SongSpec.model_validate_json(song_spec_json)
        init_midi_store(session_id, song_spec)
        print(f"=== MIDI store initialized with stems: {list(song_spec.stems.keys())} ===", flush=True)
    except Exception as e:
        print(f"=== ERROR initializing MIDI store: {e} ===", flush=True)
        yield {"type": "error", "message": f"Failed to initialize: {e}"}
        return

    # Build a "lite" song spec summary without base64 MIDI data for the prompt
    stem_summary = []
    for stem_name, stem in song_spec.stems.items():
        has_midi = "yes" if stem.midi_data else "no"
        stem_summary.append(f"  - {stem_name}: role={stem.role.value}, has_midi={has_midi}")

    structure_summary = [
        f"  - {s.name}: {s.start:.1f}s - {s.end:.1f}s"
        for s in song_spec.structure.sections
    ]

    # Build the initial prompt for the agent
    print(f"=== Building prompt ===", flush=True)
    prompt = f"""Start the song recreation workflow.

## Input Data
- Session ID: {session_id}
- Original Audio: {original_audio_path}
- Output Directory: {output_dir}
- Max Iterations: {max_iterations}
- Quality Threshold: {quality_threshold * 100:.0f}%

## Song Metadata
- Tempo: {song_spec.metadata.tempo_bpm} BPM
- Key: {song_spec.metadata.key}
- Time Signature: {song_spec.metadata.time_signature}
- Duration: {song_spec.metadata.duration_seconds:.1f} seconds

## Available Stems (MIDI is stored in the MIDI store, access via session_id)
{chr(10).join(stem_summary)}

## Song Structure
{chr(10).join(structure_summary)}

## Important Notes
- The MIDI data is stored in an internal store, NOT in this prompt
- Use get_midi_summary(session_id, stem_name) to understand MIDI content
- Use transpose_midi/quantize_midi to modify MIDI between iterations
- Pass session_id (not song_spec_json) to execute_plan

## Full Song Spec JSON (for generate_plan tool only)
{song_spec_json}

Begin by generating a plan using the generate_plan tool with the song_spec_json above.
After generating the plan, execute it using session_id="{session_id}" and evaluate the result.
Continue iterating until quality threshold is reached or max iterations exceeded.
"""

    user_content = types.Content(
        role="user",
        parts=[types.Part(text=prompt)],
    )

    iteration = 0
    print(f"=== Prompt length: {len(prompt)} chars ===", flush=True)
    print(f"=== Prompt preview: {prompt[:500]}... ===", flush=True)
    print(f"=== About to call runner.run_async ===", flush=True)

    yield {
        "type": "log",
        "message": "Waiting for AI agent to generate plan...",
    }

    with start_trace(name="songclone-workflow", session_id=session_id):
        # Emit trace URL immediately after starting trace
        trace_url = print_trace_link(f"session:{session_id}")
        if trace_url:
            yield {
                "type": "trace_url",
                "url": trace_url,
            }

        try:
            event_stream = runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=user_content,
            )
            print(f"=== runner.run_async returned event_stream ===", flush=True)
            try:
                async for event in event_stream:
                    event_type = type(event).__name__

                    # Debug: inspect event structure
                    has_content = hasattr(event, "content") and event.content is not None
                    has_tool_calls = hasattr(event, "tool_calls") and event.tool_calls
                    has_tool_responses = hasattr(event, "tool_responses") and event.tool_responses
                    is_final = event.is_final_response() if hasattr(event, "is_final_response") else False

                    print(f"=== ADK Event: {event_type} | content={has_content} | tool_calls={has_tool_calls} | tool_responses={has_tool_responses} | final={is_final} ===", flush=True)

                    # Debug: Print raw event attributes
                    print(f"===   Event attrs: {[a for a in dir(event) if not a.startswith('_')]} ===", flush=True)
                    if hasattr(event, 'author'):
                        print(f"===   Author: {event.author} ===", flush=True)
                    if hasattr(event, 'actions'):
                        print(f"===   Actions: {event.actions} ===", flush=True)

                    # If event has content with parts, inspect them
                    if has_content and hasattr(event.content, "parts"):
                        for i, part in enumerate(event.content.parts):
                            part_type = type(part).__name__
                            if hasattr(part, "function_call"):
                                fc = part.function_call
                                print(f"===   Part {i}: {part_type} -> function_call: {fc.name if hasattr(fc, 'name') else fc} ===", flush=True)
                            elif hasattr(part, "function_response"):
                                fr = part.function_response
                                print(f"===   Part {i}: {part_type} -> function_response: {fr.name if hasattr(fr, 'name') else fr} ===", flush=True)
                            elif hasattr(part, "text"):
                                text_preview = part.text[:100] if part.text else ""
                                print(f"===   Part {i}: {part_type} -> text: {text_preview}... ===", flush=True)

                    logger.debug(f"ADK Event: {event_type}")

                    # Yield structured events for SSE
                    # Check for tool calls in event.tool_calls OR in content.parts
                    tool_calls_found = []

                    if hasattr(event, "tool_calls") and event.tool_calls:
                        tool_calls_found.extend(event.tool_calls)

                    # Also check content.parts for function_call
                    if has_content and hasattr(event.content, "parts"):
                        for part in event.content.parts:
                            if hasattr(part, "function_call") and part.function_call:
                                tool_calls_found.append(part.function_call)

                    for tool_call in tool_calls_found:
                        tool_name = tool_call.name if hasattr(tool_call, "name") else str(tool_call)
                        yield {
                            "type": "tool_call",
                            "tool": tool_name,
                            "args": tool_call.args if hasattr(tool_call, "args") else {},
                        }
                        logger.info(f"Tool call: {tool_name}")
                        print(f"=== TOOL CALL: {tool_name} ===", flush=True)

                        # Emit human-readable log messages
                        if tool_name == "generate_plan":
                            yield {"type": "log", "message": "🎵 AI is generating a recreation plan..."}
                        elif tool_name == "execute_plan":
                            yield {"type": "log", "message": "🎹 Executing plan in REAPER DAW..."}
                        elif tool_name == "evaluate_recreation":
                            yield {"type": "log", "message": "🔍 Evaluating recreation quality..."}

                    # Check for tool responses in event.tool_responses OR in content.parts
                    tool_responses_found = []

                    if hasattr(event, "tool_responses") and event.tool_responses:
                        tool_responses_found.extend(event.tool_responses)

                    # Also check content.parts for function_response
                    if has_content and hasattr(event.content, "parts"):
                        for part in event.content.parts:
                            if hasattr(part, "function_response") and part.function_response:
                                tool_responses_found.append(part.function_response)

                    for tool_response in tool_responses_found:
                        tool_name = tool_response.name if hasattr(tool_response, "name") else "unknown"

                        # Debug: print tool_response structure
                        tr_attrs = [a for a in dir(tool_response) if not a.startswith('_')]
                        print(f"=== TOOL RESPONSE ATTRS for {tool_name}: {tr_attrs} ===", flush=True)

                        # Check the actual response content for error status
                        # Tools return {"status": "error", "error_message": "..."} on failure
                        response_data = None
                        status = "success"
                        error_message = None

                        if hasattr(tool_response, "response"):
                            response_data = tool_response.response
                            print(f"=== TOOL RESPONSE DATA (response): {type(response_data)} = {str(response_data)[:200]} ===", flush=True)
                        elif hasattr(tool_response, "result"):
                            response_data = tool_response.result
                            print(f"=== TOOL RESPONSE DATA (result): {type(response_data)} = {str(response_data)[:200]} ===", flush=True)
                        else:
                            print(f"=== TOOL RESPONSE: no response/result attr ===", flush=True)

                        # Check if response indicates an error
                        if isinstance(response_data, dict):
                            if response_data.get("status") == "error":
                                status = "error"
                                error_message = response_data.get("error_message", "Unknown error")

                        # Fallback: check for error attribute on response object
                        if status == "success" and hasattr(tool_response, "error") and tool_response.error:
                            status = "error"
                            error_message = str(tool_response.error)

                        yield {
                            "type": "tool_response",
                            "tool": tool_name,
                            "status": status,
                        }
                        print(f"=== TOOL RESPONSE: {tool_name} -> {status} ===", flush=True)

                        # Emit completion messages or errors
                        if status == "success":
                            if tool_name == "generate_plan":
                                yield {"type": "log", "message": "✓ Plan generated successfully"}
                            elif tool_name == "execute_plan":
                                yield {"type": "log", "message": "✓ Plan executed in REAPER"}
                            elif tool_name == "evaluate_recreation":
                                yield {"type": "log", "message": "✓ Evaluation complete"}
                        else:
                            # Emit error log
                            yield {
                                "type": "log",
                                "level": "error",
                                "message": f"✗ {tool_name} failed: {error_message}",
                            }

                            # Check for REAPER connection failure specifically
                            if error_message and "REAPER connection failed" in error_message:
                                yield {
                                    "type": "human_action_required",
                                    "description": "REAPER DAW is not running or not accessible",
                                    "reason": error_message,
                                    "steps": [
                                        "Open REAPER DAW application",
                                        "Ensure ReaScript API is enabled (Options > Preferences > Plug-ins > ReaScript)",
                                        "Run: reapy.configure_reaper() from Python if first time setup",
                                        "Click Resume when REAPER is ready",
                                    ],
                                }
                                # Signal pause state so routes.py can save context
                                yield {
                                    "type": "paused",
                                    "reason": "REAPER connection failed",
                                }
                                # Stop the generator to actually pause
                                logger.info(f"Pausing ADK session {session_id} due to REAPER failure")
                                return

                    # Check for final response
                    if event.is_final_response():
                        if event.content and event.content.parts:
                            response_text = event.content.parts[0].text
                            yield {
                                "type": "agent_response",
                                "content": response_text,
                            }
                            logger.info(f"Agent final response received")

                            # Check if we need to continue (agent will indicate in response)
                            if "continue" in response_text.lower() and iteration < max_iterations:
                                iteration += 1
                                yield {
                                    "type": "iteration",
                                    "number": iteration,
                                    "status": "started",
                                }
                                continue_content = types.Content(
                                    role="user",
                                    parts=[types.Part(text="Continue with the next iteration based on the evaluation feedback.")],
                                )
                                cont_stream = runner.run_async(
                                    user_id=user_id,
                                    session_id=session_id,
                                    new_message=continue_content,
                                )
                                try:
                                    async for cont_event in cont_stream:
                                        if cont_event.is_final_response():
                                            if cont_event.content and cont_event.content.parts:
                                                yield {
                                                    "type": "agent_response",
                                                    "content": cont_event.content.parts[0].text,
                                                }
                                            break
                                finally:
                                    await cont_stream.aclose()
                        break
            finally:
                await event_stream.aclose()

        except Exception as e:
            logger.error(f"ADK orchestrator error: {e}")
            yield {
                "type": "error",
                "message": str(e),
            }

    yield {
        "type": "complete",
        "iterations": iteration,
    }


async def send_message_to_agent(
    session_id: str,
    message: str,
    user_id: str = "user",
) -> AsyncGenerator[dict, None]:
    """
    Send a message to an existing agent session.

    Useful for resuming or interacting with a paused session.

    Args:
        session_id: Session to send message to
        message: User message
        user_id: User identifier

    Yields:
        Event dictionaries
    """
    runner = get_runner()

    user_content = types.Content(
        role="user",
        parts=[types.Part(text=message)],
    )

    with start_trace(name="songclone-message", session_id=session_id):
        trace_url = print_trace_link(f"message:{session_id}")
        if trace_url:
            yield {
                "type": "trace_url",
                "url": trace_url,
            }

        try:
            event_stream = runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=user_content,
            )
            try:
                async for event in event_stream:
                    # Check for tool calls in event.tool_calls OR in content.parts
                    tool_calls_found = []
                    has_content = hasattr(event, "content") and event.content is not None

                    if hasattr(event, "tool_calls") and event.tool_calls:
                        tool_calls_found.extend(event.tool_calls)

                    if has_content and hasattr(event.content, "parts"):
                        for part in event.content.parts:
                            if hasattr(part, "function_call") and part.function_call:
                                tool_calls_found.append(part.function_call)

                    for tool_call in tool_calls_found:
                        tool_name = tool_call.name if hasattr(tool_call, "name") else str(tool_call)
                        yield {
                            "type": "tool_call",
                            "tool": tool_name,
                            "args": tool_call.args if hasattr(tool_call, "args") else {},
                        }

                    # Check for tool responses
                    tool_responses_found = []

                    if hasattr(event, "tool_responses") and event.tool_responses:
                        tool_responses_found.extend(event.tool_responses)

                    if has_content and hasattr(event.content, "parts"):
                        for part in event.content.parts:
                            if hasattr(part, "function_response") and part.function_response:
                                tool_responses_found.append(part.function_response)

                    for tool_response in tool_responses_found:
                        tool_name = tool_response.name if hasattr(tool_response, "name") else "unknown"
                        response_data = None
                        status = "success"
                        error_message = None

                        if hasattr(tool_response, "response"):
                            response_data = tool_response.response
                        elif hasattr(tool_response, "result"):
                            response_data = tool_response.result

                        if isinstance(response_data, dict):
                            if response_data.get("status") == "error":
                                status = "error"
                                error_message = response_data.get("error_message", "Unknown error")

                        if status == "success" and hasattr(tool_response, "error") and tool_response.error:
                            status = "error"
                            error_message = str(tool_response.error)

                        yield {
                            "type": "tool_response",
                            "tool": tool_name,
                            "status": status,
                        }

                        # Check for REAPER connection failure
                        if status == "error" and error_message and "REAPER connection failed" in error_message:
                            yield {
                                "type": "human_action_required",
                                "description": "REAPER DAW is not running or not accessible",
                                "reason": error_message,
                                "steps": [
                                    "Open REAPER DAW application",
                                    "Ensure ReaScript API is enabled (Options > Preferences > Plug-ins > ReaScript)",
                                    "Run: reapy.configure_reaper() from Python if first time setup",
                                    "Click Resume when REAPER is ready",
                                ],
                            }
                            yield {
                                "type": "paused",
                                "reason": "REAPER connection failed",
                            }
                            logger.info(f"Pausing ADK session {session_id} due to REAPER failure during resume")
                            return

                    if event.is_final_response():
                        if event.content and event.content.parts:
                            yield {
                                "type": "agent_response",
                                "content": event.content.parts[0].text,
                            }
                        break
            finally:
                await event_stream.aclose()

        except Exception as e:
            yield {
                "type": "error",
                "message": str(e),
            }
