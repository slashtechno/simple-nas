#!/usr/bin/env python3
"""Check that every image pinned in group_vars/all/versions.yml has arm64 and amd64 builds.

Needs the docker CLI and network access, so it is not part of `just check`: run `just platforms`
after changing a version. Standard library only.
"""
import re
import subprocess
import sys
from pathlib import Path

VERSIONS = Path(__file__).resolve().parent.parent / "group_vars/all/versions.yml"
WANTED = {"arm64", "amd64"}

# name: value lines. A value may contain {{ other_name }}, filled in from the same file.
values = dict(re.findall(r'^([a-z0-9_]+): *"?([^"#\n]+?)"? *(?:#.*)?$', VERSIONS.read_text(), re.M))
images = {}
for name, value in values.items():
    if name.endswith("_image"):
        images[name] = re.sub(r"\{\{ *(\w+) *\}\}", lambda m: values[m.group(1)], value)

failed = False
for name, image in sorted(images.items()):
    # docker rejects a reference with both a tag and a digest; the digest alone names the image.
    reference = re.sub(r":[^:/@]+@", "@", image)
    result = subprocess.run(["docker", "manifest", "inspect", reference], capture_output=True, text=True)
    found = set(re.findall(r'"architecture": *"(\w+)"', result.stdout))
    missing = WANTED - found
    if result.returncode != 0:
        print(f"ERROR   {name}: {image}: {result.stderr.strip()}")
    elif missing:
        print(f"MISSING {name}: {image} lacks {sorted(missing)}")
    else:
        print(f"ok      {name}: {image}")
    failed = failed or result.returncode != 0 or bool(missing)
sys.exit(1 if failed else 0)
