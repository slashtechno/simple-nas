#!/usr/bin/env python3
"""Fails when a `file.md#anchor` reference, in any doc, comment or message, names a heading that does not exist.

    python3 tools/check_links.py

Anchors follow GitHub's rule: the heading in lower case, punctuation removed, spaces turned into dashes.
Standard library only.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SKIP = {".git", ".ansible"}
SUFFIXES = {".md", ".yml", ".j2", ".py", ".example", ".html", ".sh"}


def slug(heading):
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def files():
    return [p for p in REPO.rglob("*") if p.is_file() and p.suffix in SUFFIXES and not SKIP & set(p.parts) and ".ignored." not in p.name]


def main():
    headings = {}
    for path in files():
        if path.suffix == ".md":
            lines = path.read_text().splitlines()
            headings[path] = {slug(line.lstrip("#")) for line in lines if re.match(r"#{1,6} ", line)}
    problems = []
    for path in files():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for match in re.finditer(r"([\w./-]*?(\w[\w-]*\.md))#([\w-]+)", text):
            name, anchor = match.group(2), match.group(3)
            targets = [h for p, h in headings.items() if p.name == name]
            if targets and not any(anchor in h for h in targets):
                problems.append(f"{path.relative_to(REPO)}: {name}#{anchor} is not a heading")
        if path.suffix == ".md":
            for match in re.finditer(r"\]\(([^)#\s:]+\.md)[)#]", text):
                if not (path.parent / match.group(1)).exists():
                    problems.append(f"{path.relative_to(REPO)}: {match.group(1)} does not exist")
            for match in re.finditer(r"\]\(#([\w-]+)\)", text):
                if match.group(1) not in headings[path]:
                    problems.append(f"{path.relative_to(REPO)}: #{match.group(1)} is not a heading")
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
