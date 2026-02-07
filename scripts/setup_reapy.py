#!/usr/bin/env python3
"""
Setup reapy connection to REAPER.

Configures reaper.ini directly (no reapy.config.configure_reaper) to avoid
recursion bugs in reapy's ConfigParser. Then restarts REAPER if needed and
tests the connection.
"""
import ctypes.util
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import threading
import time

# =============================================================================
# Config
# =============================================================================

WEB_INTERFACE_PORT = 2307


# =============================================================================
# Helpers
# =============================================================================

def is_reaper_running():
    result = subprocess.run(["pgrep", "-x", "REAPER"], capture_output=True, timeout=5)
    return result.returncode == 0


def get_reaper_resource_path():
    """Find REAPER's resource directory."""
    if sys.platform == "darwin":
        path = os.path.expanduser("~/Library/Application Support/REAPER")
    elif sys.platform == "win32":
        path = os.path.expandvars(r"%APPDATA%\REAPER")
    else:
        path = os.path.expanduser("~/.config/REAPER")

    if os.path.exists(os.path.join(path, "reaper.ini")):
        return path

    print(f"✗ Could not find reaper.ini at {path}")
    print("  Make sure REAPER has been launched at least once.")
    sys.exit(1)


def find_python_dylib():
    """Find the Python shared library (.dylib/.so) for REAPER's ReaScript config."""
    suffix = ".dylib" if sys.platform == "darwin" else ".so"
    version = sysconfig.get_config_var("VERSION") or f"{sys.version_info.major}.{sys.version_info.minor}"

    # Candidate filenames (must end in .dylib/.so - REAPER rejects bare framework binaries)
    names = [
        f"libpython{version}{suffix}",
        f"libpython{version}m{suffix}",
        sysconfig.get_config_var("LDLIBRARY"),
    ]

    # Candidate directories
    dirs = [
        sysconfig.get_config_var("LIBPL"),
        sysconfig.get_config_var("LIBDIR"),
        sysconfig.get_config_var("srcdir"),
        os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "lib"),
    ]

    for d in filter(None, dirs):
        for name in filter(None, names):
            full = os.path.join(d, name)
            if os.path.exists(full) and full.endswith(suffix):
                return full

    print(f"✗ Could not find Python shared library ({suffix})")
    print(f"  Searched dirs: {dirs}")
    print(f"  Try: find /opt/homebrew -name 'libpython{version}*{suffix}'")
    sys.exit(1)


def configure_reaper_ini(resource_path):
    """
    Edit reaper.ini directly to enable reapy. Returns True if changes were made.

    Adds/updates:
      - reascript=1
      - pythonlibpath64=<dir>
      - pythonlibdll64=<filename>
      - csurf entry for HTTP web interface on port 2307
    """
    ini_path = os.path.join(resource_path, "reaper.ini")
    with open(ini_path, "r", encoding="utf-8") as f:
        content = f.read()

    original = content

    # --- Enable ReaScript ---
    if re.search(r"^reascript=", content, re.MULTILINE):
        content = re.sub(r"^reascript=.*$", "reascript=1", content, flags=re.MULTILINE)
    else:
        content = _insert_in_reaper_section(content, "reascript=1")

    # --- Set Python library path ---
    dylib = find_python_dylib()
    lib_dir = os.path.dirname(dylib)
    lib_name = os.path.basename(dylib)
    print(f"  Python lib: {dylib}")

    for key, val in [("pythonlibpath64", lib_dir), ("pythonlibdll64", lib_name)]:
        if re.search(rf"^{key}=", content, re.MULTILINE):
            content = re.sub(rf"^{key}=.*$", f"{key}={val}", content, flags=re.MULTILINE)
        else:
            content = _insert_in_reaper_section(content, f"{key}={val}")

    # --- Add HTTP web interface for reapy (port 2307) ---
    if f" {WEB_INTERFACE_PORT} " not in content:
        m = re.search(r"^csurf_cnt=(\d+)", content, re.MULTILINE)
        if m:
            count = int(m.group(1))
            content = re.sub(
                r"^csurf_cnt=\d+", f"csurf_cnt={count + 1}", content, flags=re.MULTILINE
            )
        else:
            count = 0
            content = _insert_in_reaper_section(content, "csurf_cnt=1")

        csurf_line = f"csurf_{count}=HTTP 0 {WEB_INTERFACE_PORT} '' 'index.html' 0 ''"
        content = _insert_in_reaper_section(content, csurf_line)

    changed = content != original
    if changed:
        backup = ini_path + ".bak"
        shutil.copy2(ini_path, backup)
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write(content)

    return changed


def _find_reapy_activation_script():
    """Find reapy's activate_reapy_server.py without importing reapy."""
    # Look in site-packages
    for path in sys.path:
        candidate = os.path.join(path, "reapy", "reascripts", "activate_reapy_server.py")
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    # Try pip show
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", "-f", "python-reapy"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        location = ""
        for line in result.stdout.split("\n"):
            if line.startswith("Location:"):
                location = line.split(":", 1)[1].strip()
        if location:
            candidate = os.path.join(location, "reapy", "reascripts", "activate_reapy_server.py")
            if os.path.exists(candidate):
                return os.path.abspath(candidate)
    return None


def _register_reapy_action(resource_path):
    """Register the reapy activation script in reaper-kb.ini and reaper-extstate.ini.

    Returns True if any files were changed (meaning REAPER needs a restart).
    """
    import random
    import string

    changed = False

    # Find the activate_reapy_server.py without importing reapy
    # (importing reapy triggers a connection attempt that would fail and poison state)
    script_path = _find_reapy_activation_script()
    if script_path is None:
        print("  (skipping action registration - reapy not installed yet)")
        return False

    if not os.path.exists(script_path):
        print(f"  (skipping action registration - script not found at {script_path})")
        return False

    # Check if already registered in reaper-kb.ini
    kb_path = os.path.join(resource_path, "reaper-kb.ini")
    if not os.path.exists(kb_path):
        open(kb_path, "w").close()

    with open(kb_path, "r") as f:
        kb_content = f.read()

    if script_path in kb_content:
        # Already registered, extract the code
        for line in kb_content.split("\n"):
            if script_path in line and line.startswith("SCR"):
                code = line.split(" ")[3].strip("_")
                action_name = f'"_{code}"'
                break
        else:
            return False
    else:
        # Generate unique action code and register
        chars = string.ascii_letters + string.digits
        code = "RS" + "".join(random.choice(chars) for _ in range(40))
        while code in kb_content:
            code = "RS" + "".join(random.choice(chars) for _ in range(40))

        script_name = os.path.basename(script_path)
        new_line = f'SCR 4 0 {code} "Custom: {script_name}" {script_path}'
        with open(kb_path, "a") as f:
            f.write(new_line + "\n")
        action_name = f'"_{code}"'
        changed = True
        print(f"  Registered reapy action in reaper-kb.ini")

    # Write ext state so reapy can find the action
    extstate_path = os.path.join(resource_path, "reaper-extstate.ini")
    if not os.path.exists(extstate_path):
        open(extstate_path, "w").close()

    with open(extstate_path, "r") as f:
        ext_content = f.read()

    if "[reapy]" not in ext_content:
        ext_content += "\n[reapy]\n"

    if "activate_reapy_server" not in ext_content:
        ext_content += f"activate_reapy_server={action_name}\n"
        with open(extstate_path, "w") as f:
            f.write(ext_content)
        changed = True
        print(f"  Wrote reapy ext state")

    return changed


def _insert_in_reaper_section(content, line):
    """Insert a line into the [REAPER] section of reaper.ini."""
    # REAPER's ini has [REAPER] as the first (often only) section
    # Insert after the section header
    m = re.search(r"^\[reaper\]", content, re.MULTILINE | re.IGNORECASE)
    if m:
        pos = m.end()
        return content[:pos] + "\n" + line + content[pos:]
    else:
        # No section header - file might start with bare keys (REAPER style)
        # Just append to the end of the first block of key=value lines
        lines = content.split("\n")
        for i, l in enumerate(lines):
            if l.startswith("[") and not l.lower().startswith("[reaper]"):
                # Hit a different section, insert before it
                lines.insert(i, line)
                return "\n".join(lines)
        # No other sections, just append
        return content.rstrip("\n") + "\n" + line + "\n"


def _activate_reapy_via_web(resource_path):
    """Trigger the reapy activation script inside REAPER via the web interface.

    This must run BEFORE `import reapy` because reapy's import-time connection
    attempt will infinitely recurse if the reapy TCP server isn't already running.

    Returns True on success, False on failure (caller should retry after restart).
    """
    from urllib import request as urlreq
    from urllib.error import URLError

    base_url = f"http://localhost:{WEB_INTERFACE_PORT}/_"

    # Check if server is already running
    try:
        resp = urlreq.urlopen(f"{base_url}/GET/EXTSTATE/reapy/server_port", timeout=1)
        text = resp.read().decode()
        # Format: "EXTSTATE\treapy\tserver_port\t2306"
        parts = text.strip().split("\t")
        if len(parts) >= 4 and parts[3]:
            print(f"  reapy server already running on port {parts[3]}")
            return True
    except (URLError, OSError):
        print("  ✗ Web interface not responding on port 2307")
        return False

    # Server not running - trigger the activation action
    try:
        resp = urlreq.urlopen(f"{base_url}/GET/EXTSTATE/reapy/activate_reapy_server", timeout=1)
        text = resp.read().decode()
        parts = text.strip().split("\t")
        if len(parts) < 4 or not parts[3]:
            print("  ✗ activate_reapy_server action not found in REAPER ext state")
            return False
        action = parts[3].strip('"')
    except (URLError, OSError) as e:
        print(f"  ✗ Failed to read ext state: {e}")
        return False

    # Call the action
    try:
        urlreq.urlopen(f"{base_url}/{action}", timeout=2)
    except (URLError, OSError) as e:
        print(f"  ✗ Failed to trigger activation action: {e}")
        return False

    # Wait for server to come up
    for i in range(10):
        time.sleep(0.5)
        try:
            resp = urlreq.urlopen(f"{base_url}/GET/EXTSTATE/reapy/server_port", timeout=1)
            text = resp.read().decode()
            parts = text.strip().split("\t")
            if len(parts) >= 4 and parts[3]:
                print(f"  ✓ reapy server activated on port {parts[3]}")
                return True
        except (URLError, OSError):
            pass

    print("  ✗ reapy server didn't start after activation")
    return False


def restart_reaper():
    """Quit and reopen REAPER."""
    print("  Quitting REAPER...")
    subprocess.run(
        ["osascript", "-e", 'tell application "REAPER" to quit'],
        capture_output=True, timeout=10,
    )
    for _ in range(20):
        if not is_reaper_running():
            break
        time.sleep(0.5)
    else:
        print("✗ REAPER didn't quit. Close it manually and re-run this script.")
        sys.exit(1)

    print("  Reopening REAPER...")
    subprocess.run(["open", "-a", "REAPER"], timeout=10)
    for _ in range(20):
        if is_reaper_running():
            break
        time.sleep(0.5)
    else:
        print("✗ REAPER didn't start. Open it manually and re-run this script.")
        sys.exit(1)

    time.sleep(3)
    print("  ✓ REAPER restarted")


def install_package(package):
    print(f"  Installing {package}...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"✗ Failed to install {package}")
        print(result.stderr)
        sys.exit(1)
    print(f"  ✓ {package} installed")


def ensure_reapy():
    try:
        import reapy
        return reapy
    except ImportError:
        print("  reapy not found, installing...")
        install_package("python-reapy")
        import reapy
        return reapy


# =============================================================================
# Main
# =============================================================================

# 1. CHECK REAPER
print("=== Checking for REAPER ===")
if not is_reaper_running():
    print("✗ REAPER is not running! Start it first, then re-run.")
    sys.exit(1)
print("✓ REAPER is running")

# 2. ENSURE REAPY INSTALLED (without importing — import triggers connection)
print("\n=== Ensuring reapy is installed ===")
result = subprocess.run(
    [sys.executable, "-m", "pip", "show", "python-reapy"],
    capture_output=True, text=True,
)
if result.returncode != 0:
    install_package("python-reapy")
else:
    print("  ✓ python-reapy already installed")

# 3. CONFIGURE reaper.ini (bypasses reapy's buggy ConfigParser)
print("\n=== Configuring reaper.ini ===")
resource_path = get_reaper_resource_path()
print(f"  Resource path: {resource_path}")
ini_changed = configure_reaper_ini(resource_path)
if ini_changed:
    print("  ✓ reaper.ini updated")
else:
    print("  ✓ reaper.ini already correct")

# 4. REGISTER REAPY ACTION in reaper-kb.ini / reaper-extstate.ini
print("\n=== Registering reapy action ===")
action_changed = _register_reapy_action(resource_path)
if action_changed:
    print("  ✓ Action registration updated")
else:
    print("  ✓ Action already registered")

# 5. RESTART REAPER IF ANY CONFIG FILES CHANGED
if ini_changed or action_changed:
    print("\n=== Restarting REAPER to load new config ===")
    restart_reaper()
else:
    # Config didn't change, but REAPER may not have been restarted since last config.
    # Check if the web interface is actually responding.
    from urllib import request as urlreq
    from urllib.error import URLError
    try:
        urlreq.urlopen(f"http://localhost:{WEB_INTERFACE_PORT}/_/GET/EXTSTATE/reapy/server_port", timeout=2)
    except (URLError, OSError):
        print("\n=== Restarting REAPER (web interface not loaded yet) ===")
        restart_reaper()

# 6. ACTIVATE REAPY SERVER VIA WEB INTERFACE (with restart-on-failure retry)
#    Must happen BEFORE `import reapy` because reapy's import triggers a
#    connection attempt that infinitely recurses if the server isn't running.
print("\n=== Activating reapy server ===")
activated = _activate_reapy_via_web(resource_path)
if not activated:
    # REAPER might be running but hasn't loaded the action list from disk.
    # Restart and retry once.
    print("\n=== Restarting REAPER and retrying activation ===")
    restart_reaper()
    activated = _activate_reapy_via_web(resource_path)
    if not activated:
        print("  ✗ reapy server failed to start after restart")
        print("    Check: REAPER > Preferences > Plug-ins > ReaScript")
        sys.exit(1)

# 7. TEST CONNECTION (safe to import reapy now that the server is running)
print("\n=== Testing connection ===")
reapy = ensure_reapy()
print(f"  reapy {reapy.__version__}")

MAX_ATTEMPTS = 3
for attempt in range(1, MAX_ATTEMPTS + 1):
    result = {"success": False, "error": None, "project": None}

    def try_connect():
        try:
            project = reapy.Project()
            _ = project.name
            result["success"] = True
            result["project"] = project
        except Exception as e:
            result["error"] = e

    thread = threading.Thread(target=try_connect, daemon=True)
    thread.start()
    thread.join(timeout=10)

    if thread.is_alive():
        result["error"] = "timed out"
    elif result["success"]:
        break

    if attempt < MAX_ATTEMPTS:
        print(f"  Attempt {attempt}/{MAX_ATTEMPTS} failed ({result['error']}), retrying...")
        time.sleep(3)

if result["success"]:
    p = result["project"]
    print(f"✓ Connected!")
    print(f"  Project: {p.name or '(untitled)'}")
    print(f"  Tempo: {p.bpm} BPM")
else:
    print(f"✗ Connection failed after {MAX_ATTEMPTS} attempts: {result['error']}")
    print("\n  Try closing REAPER completely, then re-run this script.")
    sys.exit(1)

print("\n=== All good! reapy is ready. ===")
