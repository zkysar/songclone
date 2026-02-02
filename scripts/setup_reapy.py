#!/usr/bin/env python3
"""
Verbose reapy setup and connection test with timeout
Auto-installs dependencies if missing.
"""
import sys
import subprocess
import threading

def install_package(package):
    """Install a package using pip"""
    print(f"  Installing {package}...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"✗ Failed to install {package}")
        print(result.stderr)
        sys.exit(1)
    print(f"  ✓ {package} installed")

def ensure_reapy():
    """Ensure reapy is installed"""
    try:
        import reapy
        return reapy
    except ImportError:
        print("  reapy not found, installing...")
        install_package("python-reapy")
        import reapy
        return reapy

def is_reaper_running():
    """Check if REAPER process is running"""
    result = subprocess.run(
        ["pgrep", "-i", "reaper"],
        capture_output=True,
        timeout=5
    )
    return result.returncode == 0

# 0. CHECK IF REAPER IS RUNNING
print("=== Checking for REAPER process ===")

if not is_reaper_running():
    print("✗ REAPER is not running!")
    print("\n  Please start REAPER first, then run this script again.")
    sys.exit(1)

print("✓ REAPER is running")

# 1. VERBOSE CONFIGURE
print("\n=== Configuring REAPER for reapy ===")
try:
    reapy = ensure_reapy()
    from reapy.config import configure_reaper, REAPY_SERVER_PORT

    print(f"reapy version: {reapy.__version__}")
    print(f"reapy location: {reapy.__file__}")
    print(f"Server port: {REAPY_SERVER_PORT}")

    print("\nRunning configure_reaper()...")
    configure_reaper()
    print("✓ Configuration complete (restart REAPER if first time)")

except Exception as e:
    print(f"✗ Configure failed: {e}")
    sys.exit(1)

# 2. TEST CONNECTION WITH TIMEOUT
print("\n=== Testing connection (5 second timeout) ===")

result = {"success": False, "error": None, "project": None}

def try_connect():
    try:
        project = reapy.Project()
        result["success"] = True
        result["project"] = project
    except Exception as e:
        result["error"] = e

thread = threading.Thread(target=try_connect)
thread.daemon = True
thread.start()
thread.join(timeout=5)

if thread.is_alive():
    print("✗ Connection timed out - reapy server not running in REAPER")
    print("\n  To fix:")
    print("  1. In REAPER: Actions menu (?) → search 'reapy' → Run the server script")
    print("  2. Then run this script again")
    sys.exit(1)
elif result["success"]:
    project = result["project"]
    print(f"✓ Connected successfully!")
    print(f"  Project: {project.name}")
    print(f"  Tempo: {project.bpm} BPM")
else:
    print(f"✗ Connection failed: {result['error']}")
    sys.exit(1)

print("\n=== All checks passed! ===")
