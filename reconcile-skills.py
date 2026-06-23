#!/usr/bin/env python3
"""
reconcile-skills.py — Wire canonical skills to teammates via symlinks.

Reads SKILL.md frontmatter for teammates: arrays, creates symlinks in
each teammate's .claude/skills/ directory pointing to canonical skills
in library/skills/. Removes stale symlinks. ORG.md is SSoT for roster.

Usage:
    python3 reconcile-skills.py              # live run
    python3 reconcile-skills.py --dry-run    # preview only
"""

import os
import sys
import re
from pathlib import Path

HONEYBLOOM = Path("/Users/deepak-macmini/honeybloom")
SKILLS_DIR = HONEYBLOOM / "library" / "skills"
ORG_MD = HONEYBLOOM / "library" / "ORG.md"

dry_run = "--dry-run" in sys.argv


def get_active_teammates():
    """Read active teammates from ORG.md Teammate: lines."""
    teammates = set()
    with open(ORG_MD, "r") as f:
        for line in f:
            m = re.match(r"^Teammate:\s+(\w+)", line.strip())
            if m:
                teammates.add(m.group(1).lower())
    return teammates


def parse_frontmatter(skill_path):
    """Parse YAML frontmatter from SKILL.md for teammates array."""
    with open(skill_path, "r") as f:
        content = f.read()

    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return []

    fm = fm_match.group(1)
    tm_match = re.search(r"^teammates:\s*\[([^\]]*)\]", fm, re.MULTILINE)
    if not tm_match:
        return []

    raw = tm_match.group(1).strip()
    if not raw:
        return []

    return [t.strip().strip('"').strip("'").lower() for t in raw.split(",") if t.strip()]


def reconcile():
    active = get_active_teammates()
    if not active:
        print("ERROR: No active teammates found in ORG.md")
        sys.exit(1)

    print(f"Active teammates: {len(active)}")
    print(f"Skills directory: {SKILLS_DIR}")

    # Collect all skills and their teammate assignments
    skill_assignments = {}
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        teammates = parse_frontmatter(skill_md)
        # Filter to active teammates only
        teammates = [t for t in teammates if t in active]
        if teammates:
            skill_assignments[skill_dir.name] = teammates

    print(f"Skills with assignments: {len(skill_assignments)}")

    created = 0
    existed = 0
    removed = 0

    # Build expected symlinks per teammate
    expected = {}  # teammate -> set of skill names
    for skill_name, teammates in skill_assignments.items():
        for t in teammates:
            expected.setdefault(t, set()).add(skill_name)

    # Create symlinks
    for skill_name, teammates in skill_assignments.items():
        canonical = SKILLS_DIR / skill_name / "SKILL.md"
        for t in teammates:
            target_dir = HONEYBLOOM / t / ".claude" / "skills" / skill_name
            target_link = target_dir / "SKILL.md"

            if target_link.is_symlink() or target_link.exists():
                existed += 1
                continue

            if dry_run:
                print(f"  [dry-run] would create: {t}/.claude/skills/{skill_name}/SKILL.md")
                created += 1
            else:
                target_dir.mkdir(parents=True, exist_ok=True)
                target_link.symlink_to(canonical)
                created += 1

    # Remove stale symlinks
    for t in active:
        skills_root = HONEYBLOOM / t / ".claude" / "skills"
        if not skills_root.exists():
            continue
        for item in skills_root.iterdir():
            if not item.is_dir():
                continue
            link = item / "SKILL.md"
            if not link.is_symlink():
                continue
            # Stale if teammate not in this skill's frontmatter
            if item.name not in expected.get(t, set()):
                if dry_run:
                    print(f"  [dry-run] would remove stale: {t}/.claude/skills/{item.name}/SKILL.md")
                else:
                    link.unlink()
                    # Remove empty directory
                    try:
                        item.rmdir()
                    except OSError:
                        pass
                removed += 1

    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{mode}Results:")
    print(f"  Symlinks created: {created}")
    print(f"  Symlinks already existed: {existed}")
    print(f"  Stale symlinks removed: {removed}")
    print(f"  Total active wiring: {created + existed}")


if __name__ == "__main__":
    reconcile()
