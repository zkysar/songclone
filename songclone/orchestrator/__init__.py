"""Agentic orchestration for song recreation workflow.

This package provides ADK-compatible agents for the song recreation workflow.

Usage with adk web:
    cd songclone
    adk web orchestrator
"""

from songclone.orchestrator.agent import root_agent

__all__ = ["root_agent"]
