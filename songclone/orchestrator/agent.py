"""ADK agent definition for the SongClone orchestrator.

This module defines the root_agent that can be used with `adk web` for debugging
and visualization of the agent's execution.

Usage:
    cd songclone
    adk web orchestrator
"""

from pathlib import Path

from google.adk.agents import Agent

from songclone.orchestrator.tools import (
    evaluate_recreation,
    execute_plan,
    generate_plan,
    get_midi_summary,
    quantize_midi,
    transpose_midi,
)

INSTRUCTION = """You are a song recreation orchestrator. Your job is to recreate songs
using REAPER DAW through an iterative refinement process.

## Workflow
1. When given a song analysis, use generate_plan to create an execution plan
2. Use execute_plan with the session_id to implement the plan in REAPER and render audio
3. Use evaluate_recreation to compare the result against the original
4. If the score is below 80% (48/60), analyze the feedback:
   - For pitch issues: use get_midi_summary + transpose_midi
   - For timing issues: use get_midi_summary + quantize_midi
   - Then re-run execute_plan with the modified MIDI
5. Repeat until quality threshold is reached or max iterations (10) exceeded

## Tool Usage
- generate_plan: Takes song_spec JSON, optional previous feedback, and iteration number
- execute_plan: Takes plan JSON, session_id (NOT song_spec!), and output path
- evaluate_recreation: Takes original and recreation audio paths

## MIDI Editing Tools
After evaluation, if feedback indicates MIDI issues:
- get_midi_summary: Understand the MIDI content (note count, pitch range, velocity, density)
- transpose_midi: Fix pitch problems by shifting notes up/down by semitones
- quantize_midi: Fix timing issues by snapping notes to a rhythmic grid (1/4, 1/8, 1/16, 1/32)

IMPORTANT: Always pass session_id to execute_plan, NOT the full song_spec_json.
The MIDI store holds the current state of all MIDI data, including any modifications.

## Guidelines
- Always start with generate_plan before execute_plan
- Pass evaluation feedback to the next generate_plan call for improvements
- Use MIDI tools to make quick adjustments between iterations
- Track iteration count and stop at max 10 iterations
- Report final score and quality assessment to the user

## Output Format
After each iteration, summarize:
- Iteration number
- Score achieved (X/60)
- Key feedback points
- MIDI modifications made (if any)
- Whether continuing or stopping
"""

root_agent = Agent(
    name="songclone_orchestrator",
    model="gemini-3-pro-preview",
    description="Orchestrates iterative song recreation using REAPER DAW",
    instruction=INSTRUCTION,
    tools=[
        generate_plan,
        execute_plan,
        evaluate_recreation,
        get_midi_summary,
        transpose_midi,
        quantize_midi,
    ],
)
