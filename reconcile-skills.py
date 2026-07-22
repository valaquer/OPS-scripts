#!/usr/bin/env python3
"""
reconcile-skills.py — Wire canonical skills to teammates via symlinks.

Reads SKILL.md frontmatter for teammates: arrays, creates symlinks in
each teammate's .claude/skills/ directory pointing to canonical skills
in library/wiki/. Removes stale symlinks. ORG.md is SSoT for roster
and team definitions.

Supports team tokens in frontmatter:
  teammates: [rio-team, gunnar]     # mixed: team + individual
  teammates: [all]                  # everyone in the org

Usage:
    python3 reconcile-skills.py              # live run
    python3 reconcile-skills.py --dry-run    # preview only
    python3 reconcile-skills.py --verify     # check all symlinks resolve + frontmatters parse
"""

import os
import sys
import re
from pathlib import Path

HONEYBLOOM = Path("/Users/deepak-macmini/honeybloom")
SKILL_DIRS = [
    HONEYBLOOM / "library" / "wiki" / "how-to-guides",
    HONEYBLOOM / "library" / "wiki" / "project-runbooks",
]
ORG_MD = HONEYBLOOM / "library" / "ORG.md"

dry_run = "--dry-run" in sys.argv
verify_mode = "--verify" in sys.argv


def get_active_teammates():
    """Read active teammates from ORG.md Teammate: lines."""
    teammates = set()
    with open(ORG_MD, "r") as f:
        for line in f:
            m = re.match(r"^Teammate:\s+(\w+)", line.strip())
            if m:
                teammates.add(m.group(1).lower())
    return teammates


def get_teams():
    """Parse ORG.md Groups section into team-token → member-set mapping.

    Groups format: 'rio, chica, natalie (host: rio)' → rio-team: {rio, chica, natalie}
    """
    teams = {}
    in_groups = False
    with open(ORG_MD, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped == "## Groups":
                in_groups = True
                continue
            if in_groups and stripped.startswith("## "):
                break
            if not in_groups or not stripped:
                continue
            m = re.match(r"^(.+?)\s*\(host:\s*(\w+)\)", stripped)
            if m:
                members_str = m.group(1)
                host = m.group(2).lower()
                members = {n.strip().lower() for n in members_str.split(",") if n.strip()}
                teams[f"{host}-team"] = members
    return teams


def expand_teammates(raw_teammates, teams, active):
    """Expand team tokens and 'all' into individual teammate names.

    Returns a list of individual teammate names (filtered to active roster).
    Fails loudly if a -team token resolves to zero members.
    Fails loudly if 'all' resolves to fewer members than the active roster.
    """
    expanded = set()
    for token in raw_teammates:
        if token == "all":
            all_from_teams = set()
            for members in teams.values():
                all_from_teams.update(members)
            if len(all_from_teams) < len(active):
                missing = active - all_from_teams
                print(f"ERROR: 'all' resolves to {len(all_from_teams)} members but roster has {len(active)}. Missing from groups: {missing}")
                sys.exit(1)
            expanded.update(all_from_teams)
        elif token.endswith("-team"):
            if token not in teams:
                print(f"ERROR: team token '{token}' not found in ORG.md Groups section")
                sys.exit(1)
            members = teams[token]
            if not members:
                print(f"ERROR: team token '{token}' resolves to zero members")
                sys.exit(1)
            expanded.update(members)
        else:
            expanded.add(token)
    return [t for t in expanded if t in active]


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


def discover_skills():
    """Walk all skill directories and return {skill_name: canonical_path} map.

    Fails loudly on name collisions across directories.
    """
    skills = {}
    for skill_dir in SKILL_DIRS:
        if not skill_dir.exists():
            continue
        for entry in sorted(skill_dir.iterdir()):
            skill_md = entry / "SKILL.md"
            if not skill_md.exists():
                continue
            name = entry.name
            if name in skills:
                print(f"ERROR: skill name collision — '{name}' found in both {skills[name].parent} and {entry}")
                sys.exit(1)
            skills[name] = skill_md
    return skills


def verify():
    """Check all symlinks resolve and all frontmatters parse."""
    active = get_active_teammates()
    teams = get_teams()
    skills = discover_skills()
    errors = 0

    for name, skill_md in sorted(skills.items()):
        try:
            raw = parse_frontmatter(skill_md)
            expand_teammates(raw, teams, active)
        except Exception as e:
            print(f"  FAIL frontmatter: {name} — {e}")
            errors += 1

    for t in active:
        skills_root = HONEYBLOOM / t / ".claude" / "skills"
        if not skills_root.exists():
            continue
        for item in skills_root.iterdir():
            if not item.is_dir():
                continue
            link = item / "SKILL.md"
            if link.is_symlink() and not link.exists():
                print(f"  BROKEN symlink: {t}/.claude/skills/{item.name}/SKILL.md -> {os.readlink(link)}")
                errors += 1

    print(f"\nVerify: {len(skills)} skills checked, {len(active)} teammates scanned, {errors} errors")
    return errors == 0


def reconcile():
    active = get_active_teammates()
    if not active:
        print("ERROR: No active teammates found in ORG.md")
        sys.exit(1)

    teams = get_teams()
    if not teams:
        print("ERROR: No teams found in ORG.md Groups section")
        sys.exit(1)

    skills = discover_skills()

    print(f"Active teammates: {len(active)}")
    print(f"Teams: {len(teams)} ({', '.join(sorted(teams.keys()))})")
    print(f"Skill sources: {', '.join(str(d) for d in SKILL_DIRS)}")
    print(f"Skills discovered: {len(skills)}")

    skill_assignments = {}
    for name, skill_md in skills.items():
        raw_teammates = parse_frontmatter(skill_md)
        teammates = expand_teammates(raw_teammates, teams, active)
        if teammates:
            skill_assignments[name] = (skill_md, teammates)

    print(f"Skills with assignments: {len(skill_assignments)}")

    created = 0
    existed = 0
    removed = 0

    expected = {}
    for skill_name, (_, teammates) in skill_assignments.items():
        for t in teammates:
            expected.setdefault(t, set()).add(skill_name)

    for skill_name, (canonical, teammates) in skill_assignments.items():
        for t in teammates:
            target_dir = HONEYBLOOM / t / ".claude" / "skills" / skill_name
            target_link = target_dir / "SKILL.md"

            if target_link.is_symlink():
                current_target = Path(os.readlink(target_link))
                if current_target == canonical:
                    existed += 1
                    continue
                if dry_run:
                    print(f"  [dry-run] would repoint: {t}/.claude/skills/{skill_name}/SKILL.md -> {canonical}")
                else:
                    target_link.unlink()
                    target_link.symlink_to(canonical)
                created += 1
                continue
            elif target_link.exists():
                existed += 1
                continue

            if dry_run:
                print(f"  [dry-run] would create: {t}/.claude/skills/{skill_name}/SKILL.md")
                created += 1
            else:
                target_dir.mkdir(parents=True, exist_ok=True)
                target_link.symlink_to(canonical)
                created += 1

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
            if item.name not in expected.get(t, set()):
                if dry_run:
                    print(f"  [dry-run] would remove stale: {t}/.claude/skills/{item.name}/SKILL.md")
                else:
                    link.unlink()
                    try:
                        item.rmdir()
                    except OSError:
                        pass
                removed += 1

    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{mode}Results:")
    print(f"  Symlinks created/repointed: {created}")
    print(f"  Symlinks already correct: {existed}")
    print(f"  Stale symlinks removed: {removed}")
    print(f"  Total active wiring: {created + existed}")


if __name__ == "__main__":
    if verify_mode:
        ok = verify()
        sys.exit(0 if ok else 1)
    reconcile()
