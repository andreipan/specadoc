#!/usr/bin/env python3
"""Initialize Specadoc proposal artifacts in a target repository."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

VALID_RISKS = ("low", "medium", "high")


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("change slug must contain at least one letter or digit")
    return slug


def title_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-"))


def render(template: str, title: str, risk: str) -> str:
    return (
        template.replace("__CHANGE_TITLE__", title)
        .replace("__RISK__", risk.capitalize())
        .replace("__DATE__", date.today().isoformat())
    )


def write_from_template(
    template_path: Path,
    destination: Path,
    title: str,
    risk: str,
    force: bool,
) -> None:
    if destination.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing file: {destination}")
    content = render(template_path.read_text(encoding="utf-8"), title, risk)
    destination.write_text(content, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create spec.md and plan.md for a Specadoc proposal."
    )
    parser.add_argument("change_slug", help="Change name, normalized to kebab-case")
    parser.add_argument(
        "--root",
        default="docs/agent",
        help="Artifact root relative to the current repository (default: docs/agent)",
    )
    parser.add_argument("--risk", choices=VALID_RISKS, default="medium")
    parser.add_argument("--with-design", action="store_true")
    parser.add_argument("--with-research", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        slug = normalize_slug(args.change_slug)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    skill_root = Path(__file__).resolve().parent.parent
    assets = skill_root / "assets"
    target = Path(args.root).resolve() / slug
    target.mkdir(parents=True, exist_ok=True)
    title = title_from_slug(slug)

    files = [
        (assets / "spec-template.md", target / "spec.md"),
        (assets / "plan-template.md", target / "plan.md"),
    ]
    if args.with_design:
        files.append((assets / "design-template.md", target / "design.md"))
    if args.with_research:
        files.append((assets / "research-template.md", target / "research.md"))

    try:
        for template_path, destination in files:
            if not template_path.exists():
                raise FileNotFoundError(f"missing bundled template: {template_path}")
            write_from_template(template_path, destination, title, args.risk, args.force)
    except (FileExistsError, FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"created change artifacts in {target}")
    for _, destination in files:
        print(f"- {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
