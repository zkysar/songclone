"""Test reapy's inside_reaper() for bulk MIDI operations."""

import time
import reapy

def test_inside_reaper_available():
    """Check if inside_reaper() context manager is available and works."""
    print("Testing reapy.inside_reaper() availability...")

    # First, connect normally
    try:
        reapy.connect()
        project = reapy.Project()
        print(f"Connected to project: {project.name}")
    except Exception as e:
        print(f"Failed to connect: {e}")
        return False

    # Check if inside_reaper exists
    if not hasattr(reapy, 'inside_reaper'):
        print("ERROR: reapy.inside_reaper() not available in this version")
        return False

    print("inside_reaper() exists, testing if it works...")

    # Try using inside_reaper
    try:
        with reapy.inside_reaper():
            project = reapy.Project()
            track_count = len(project.tracks)
            print(f"  Inside context: {track_count} tracks")
        print("SUCCESS: inside_reaper() works!")
        return True
    except Exception as e:
        print(f"ERROR: inside_reaper() failed: {e}")
        print(f"  Type: {type(e).__name__}")
        return False


def benchmark_midi_insertion():
    """Benchmark normal vs inside_reaper MIDI insertion."""
    reapy.connect()
    project = reapy.Project()

    # Create a test track
    test_track_idx = len(project.tracks)
    project.add_track(index=test_track_idx, name="MIDI Benchmark Test")
    track = project.tracks[test_track_idx]

    # Create test notes (100 notes)
    notes = [
        {"pitch": 60 + (i % 12), "start": i * 0.1, "length": 0.08, "velocity": 80}
        for i in range(100)
    ]

    # Test 1: Normal insertion (one IPC call per note)
    print("\n--- Test 1: Normal insertion (100 notes) ---")
    item1 = track.add_midi_item(0, 12)
    take1 = item1.active_take

    start = time.perf_counter()
    for note in notes:
        take1.add_note(
            start=note["start"],
            end=note["start"] + note["length"],
            pitch=note["pitch"],
            velocity=note["velocity"],
            channel=0
        )
    elapsed_normal = time.perf_counter() - start
    print(f"Normal insertion: {elapsed_normal:.3f}s ({elapsed_normal/len(notes)*1000:.1f}ms per note)")

    # Test 2: inside_reaper insertion
    print("\n--- Test 2: inside_reaper() insertion (100 notes) ---")
    item2 = track.add_midi_item(15, 27)

    try:
        start = time.perf_counter()
        with reapy.inside_reaper():
            # Re-get objects inside the context
            proj = reapy.Project()
            trk = proj.tracks[test_track_idx]
            # Find item2 by position
            for itm in trk.items:
                if abs(itm.position - 15) < 0.1:
                    take2 = itm.active_take
                    break
            else:
                raise Exception("Couldn't find item2")

            for note in notes:
                take2.add_note(
                    start=note["start"],
                    end=note["start"] + note["length"],
                    pitch=note["pitch"],
                    velocity=note["velocity"],
                    channel=0
                )
        elapsed_inside = time.perf_counter() - start
        print(f"inside_reaper insertion: {elapsed_inside:.3f}s ({elapsed_inside/len(notes)*1000:.1f}ms per note)")
        print(f"\nSpeedup: {elapsed_normal/elapsed_inside:.1f}x faster")
    except Exception as e:
        print(f"inside_reaper test failed: {e}")
        elapsed_inside = None

    # Cleanup - delete test track
    print("\nCleaning up test track...")
    track.delete()
    print("Done!")

    return elapsed_normal, elapsed_inside


if __name__ == "__main__":
    print("=" * 50)
    print("reapy inside_reaper() Test")
    print("=" * 50)

    if test_inside_reaper_available():
        print("\n" + "=" * 50)
        print("Running benchmark...")
        print("=" * 50)
        benchmark_midi_insertion()
    else:
        print("\ninside_reaper() not available - try alternative approaches")
