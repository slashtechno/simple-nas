#!/usr/bin/env python3
"""The after-unlock hook (00-containers.sh) starts the containers that a lock stopped, in an order that works.

Runs the rendered hook (the path is the argument) with a fake docker. The fake refuses to start a container that joins another
container's network (network_mode: container:<name>) until that one is running, as Docker does. Standard library only.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

work = Path(tempfile.mkdtemp(dir="/tmp"))
bin_dir = work / "bin"
bin_dir.mkdir()
(bin_dir / "docker").write_text("""#!/bin/bash
# A fake docker. $FAKE holds: names (one per line), mode.<name> (the network mode), started (what has been started, in order).
case "$1" in
  ps) cat "$FAKE/names" ;;
  inspect)
    case "$3" in
      *NetworkMode*) cat "$FAKE/mode.$4" 2>/dev/null || echo default ;;
      *State.Status*) echo exited ;;
    esac ;;
  start)
    mode=$(cat "$FAKE/mode.$2" 2>/dev/null || echo default)
    case "$mode" in
      container:*) grep -qx "${mode#container:}" "$FAKE/started" 2>/dev/null || { echo "cannot join network namespace of a non running container" >&2; exit 1; } ;;
    esac
    echo "$2" >> "$FAKE/started" ;;
esac
""")
(bin_dir / "docker").chmod(0o755)

stopped = work / "stopped"
script = Path(sys.argv[1]).read_text()
script = re.sub(r"STOPPED_FILE=\S+", f"STOPPED_FILE={stopped}", script)
(work / "hook.sh").write_text(script)

# The lock stopped the containers that join the network first, as on a real host, and the one they join last.
(work / "names").write_text("joiner-a\njoiner-b\nhost-net\nplain\n")
(work / "mode.joiner-a").write_text("container:vpn")
(work / "mode.joiner-b").write_text("container:vpn")
(work / "mode.vpn").write_text("default")
(work / "names").write_text("joiner-a\njoiner-b\nvpn\nplain\n")
stopped.write_text("joiner-a\njoiner-b\nvpn\nplain\n")

done = subprocess.run(["bash", str(work / "hook.sh")], capture_output=True, text=True, timeout=30,
                      env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE": str(work)})
started = (work / "started").read_text().split()
assert done.returncode == 0, (done.returncode, done.stdout, done.stderr)
assert sorted(started) == ["joiner-a", "joiner-b", "plain", "vpn"], started
assert started.index("vpn") < started.index("joiner-a") and started.index("vpn") < started.index("joiner-b"), started
assert not stopped.exists()  # the list is used up

print("00-containers.sh: containers that join another's network start after it")
