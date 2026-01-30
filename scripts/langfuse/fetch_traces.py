#!/usr/bin/env python3
"""Fetch Langfuse traces and save them locally for analysis."""

import json
import os
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")

OUTPUT_DIR = Path(__file__).parent / "traces"


def fetch_traces(limit: int = 50, page: int = 1) -> dict:
    """Fetch list of traces from Langfuse API."""
    url = f"{BASE_URL}/api/public/traces"
    response = httpx.get(
        url,
        params={"limit": limit, "page": page},
        auth=(PUBLIC_KEY, SECRET_KEY),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_trace_detail(trace_id: str) -> dict:
    """Fetch full trace details including all observations."""
    url = f"{BASE_URL}/api/public/traces/{trace_id}"
    response = httpx.get(
        url,
        auth=(PUBLIC_KEY, SECRET_KEY),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_observations(trace_id: str) -> dict:
    """Fetch all observations for a trace."""
    url = f"{BASE_URL}/api/public/observations"
    response = httpx.get(
        url,
        params={"traceId": trace_id, "limit": 100},
        auth=(PUBLIC_KEY, SECRET_KEY),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def save_trace(trace: dict, observations: dict, output_dir: Path) -> Path:
    """Save trace and observations to a JSON file."""
    trace_id = trace.get("id", "unknown")
    timestamp = trace.get("timestamp", datetime.now().isoformat())

    # Create filename from timestamp and trace name
    name = trace.get("name", "unnamed")[:30].replace("/", "-").replace(" ", "_")
    date_str = timestamp[:10] if timestamp else "unknown"
    filename = f"{date_str}_{name}_{trace_id[:8]}.json"

    output_path = output_dir / filename

    data = {
        "trace": trace,
        "observations": observations.get("data", []),
    }

    output_path.write_text(json.dumps(data, indent=2, default=str))
    return output_path


def main():
    if not PUBLIC_KEY or not SECRET_KEY:
        print("Error: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set")
        return

    OUTPUT_DIR.mkdir(exist_ok=True)

    print(f"Fetching traces from {BASE_URL}...")

    traces_response = fetch_traces(limit=50)
    traces = traces_response.get("data", [])

    print(f"Found {len(traces)} traces")

    for i, trace_summary in enumerate(traces):
        trace_id = trace_summary["id"]
        name = trace_summary.get("name", "unnamed")

        print(f"[{i+1}/{len(traces)}] Fetching: {name} ({trace_id[:8]}...)")

        try:
            trace_detail = fetch_trace_detail(trace_id)
            observations = fetch_observations(trace_id)

            output_path = save_trace(trace_detail, observations, OUTPUT_DIR)
            print(f"  Saved to: {output_path.name}")
        except Exception as e:
            print(f"  Error: {e}")

    print(f"\nTraces saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
