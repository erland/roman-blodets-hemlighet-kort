#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

CHAPTER_FILE_RE = re.compile(r"kapitel-(\d{2})\.md$")
CHAPTER_H1_RE = re.compile(r"^#\s+Kapitel\s+(\d+)\s+[–-]\s+(.+?)\s*$")
MARKERS = (
    "TODO",
    "FIXME",
    "[PLACEHOLDER]",
    "Kort kapitelnotering:",
    "## Kapitelnotering",
    "## Dialog- och röstrevision",
    "## Språkrevision",
    "## Efter kapitel",
)

REQUIRED_PATHS = (
    "README.md",
    "project-manifest.json",
    "roman-bibel.md",
    "synopsis.md",
    "kapitelplan.md",
    "projektstatus.md",
    "project-index.md",
    "kapitel",
    "omslag/cover.jpg",
    "publishing/metadata.yaml",
    "publishing/epub.css",
    "publishing/fix-epub-after-pandoc.py",
    "publishing/pdf-template.tex",
    "publishing/pdf-filter.lua",
    "scripts/build_book.py",
)

REQUIRED_METADATA_KEYS = ("title", "subtitle", "author", "language", "cover-image")
EXPECTED_TITLE = "Blodets hemlighet"
EXPECTED_SUBTITLE = "Den första gnistan"
EXPECTED_AUTHOR = "Erland Lindmark"


def error(errors: list[str], message: str) -> None:
    errors.append(message)
    print(f"ERROR: {message}", file=sys.stderr)


def parse_simple_yaml_scalars(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def validate_markdown_links(root: Path, errors: list[str]) -> None:
    link_re = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    for md in sorted(root.rglob("*.md")):
        if ".git" in md.relative_to(root).parts:
            continue
        text = md.read_text(encoding="utf-8")
        for target in link_re.findall(text):
            target = target.strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            if " " in target and not target.startswith(("./", "../")):
                target = target.split(" ", 1)[0]
            target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not target:
                continue
            candidate = (md.parent / target).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                continue
            if not candidate.exists():
                error(errors, f"Trasig intern Markdown-länk i {md.relative_to(root)}: {target}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors: list[str] = []

    if not root.is_dir():
        error(errors, f"Projektkatalogen finns inte: {root}")
        return 1

    for rel in REQUIRED_PATHS:
        if not (root / rel).exists():
            error(errors, f"Obligatorisk projektsökväg saknas: {rel}")
    if errors:
        return 1

    try:
        manifest = json.loads((root / "project-manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        error(errors, f"project-manifest.json är ogiltig: {exc}")
        return 1

    canonical: dict[int, Path] = {}
    for path in sorted((root / "kapitel").iterdir()):
        if not path.is_file():
            continue
        match = CHAPTER_FILE_RE.fullmatch(path.name)
        if match:
            canonical[int(match.group(1))] = path

    numbers = sorted(canonical)
    if not numbers:
        error(errors, "Inga kapitel hittades.")
    else:
        expected = list(range(1, numbers[-1] + 1))
        missing = sorted(set(expected) - set(numbers))
        if missing:
            error(errors, "Kapitel saknas: " + ", ".join(map(str, missing)))

    manifest_chapters = manifest.get("chapters", {})
    if manifest_chapters.get("count") != len(numbers):
        error(errors, f"Manifestets kapitelantal matchar inte filerna ({len(numbers)}).")
    if numbers and manifest_chapters.get("latest") != numbers[-1]:
        error(errors, "Manifestets senaste kapitel matchar inte kapitelfilerna.")

    for number, path in sorted(canonical.items()):
        text = path.read_text(encoding="utf-8")
        stripped = text.strip()
        if not stripped:
            error(errors, f"{path.relative_to(root)} är tom.")
            continue
        first_line = stripped.splitlines()[0].strip()
        match = CHAPTER_H1_RE.fullmatch(first_line)
        if not match:
            error(errors, f"{path.relative_to(root)} har fel H1-format; väntat '# Kapitel {number} – Titel'.")
        elif int(match.group(1)) != number:
            error(errors, f"{path.relative_to(root)} har fel kapitelnummer i H1.")
        for marker in MARKERS:
            if marker in text:
                error(errors, f"{path.relative_to(root)} innehåller intern arbetsmarkör: {marker}")

    metadata = parse_simple_yaml_scalars(root / "publishing/metadata.yaml")
    for key in REQUIRED_METADATA_KEYS:
        if not metadata.get(key):
            error(errors, f"publishing/metadata.yaml saknar värde för '{key}'.")
    if metadata.get("title") != EXPECTED_TITLE:
        error(errors, "Metadatafältet title matchar inte projektets titel.")
    if metadata.get("subtitle") != EXPECTED_SUBTITLE:
        error(errors, "Metadatafältet subtitle matchar inte projektets undertitel.")
    if metadata.get("author") != EXPECTED_AUTHOR:
        error(errors, "Metadatafältet author matchar inte projektets författare.")

    project = manifest.get("project", {})
    if project.get("title") != EXPECTED_TITLE:
        error(errors, "Manifestets titel är fel.")
    if project.get("subtitle") != EXPECTED_SUBTITLE:
        error(errors, "Manifestets undertitel är fel.")
    if project.get("author") != EXPECTED_AUTHOR:
        error(errors, "Manifestets författare är fel.")

    validate_markdown_links(root, errors)

    if errors:
        print(f"\nValidation failed: {len(errors)} error(s).", file=sys.stderr)
        return 1

    print(f"OK: projektvalidering godkänd. {len(numbers)} kapitel, senaste kapitel {numbers[-1]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
