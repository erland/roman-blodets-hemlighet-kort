#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

PANDOC_VERSION = "3.1.11.1"
XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
OPF_NS = "http://www.idpf.org/2007/opf"
SOURCE_H1_RE = re.compile(r"^#\s+Kapitel\s+(\d+)\s+[–-]\s+(.+?)\s*$")


def simple_metadata(path: Path) -> dict[str, str]:
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


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")


def pandoc_version() -> str:
    result = subprocess.run(["pandoc", "--version"], text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError("Pandoc finns inte i PATH.")
    first = result.stdout.splitlines()[0]
    match = re.search(r"pandoc\s+([0-9][^\s]*)", first)
    return match.group(1) if match else first


def normalized_chapters(root: Path, temp: Path) -> list[Path]:
    out: list[Path] = []
    chapters = sorted(
        (root / "kapitel").glob("kapitel-[0-9][0-9].md"),
        key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)),
    )
    for path in chapters:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines:
            raise RuntimeError(f"Tom kapitelfil: {path}")
        match = SOURCE_H1_RE.fullmatch(lines[0].strip())
        if not match:
            raise RuntimeError(f"Fel kapitelrubrik i {path.name}.")
        lines[0] = f"# {match.group(1)}. {match.group(2)}"
        target = temp / path.name
        target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        out.append(target)
    return out


def validate_epub(path: Path, expected_chapters: int, title: str) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if not names or names[0] != "mimetype":
            raise RuntimeError("EPUB-fel: mimetype ligger inte först.")
        if archive.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            raise RuntimeError("EPUB-fel: mimetype är komprimerad.")

        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
        if rootfile is None:
            raise RuntimeError("EPUB-fel: OPF-root saknas.")
        opf_name = rootfile.attrib["full-path"]
        opf = ET.fromstring(archive.read(opf_name))
        ns = {"opf": OPF_NS}
        manifest = opf.find("opf:manifest", ns)
        spine = opf.find("opf:spine", ns)
        if manifest is None or spine is None:
            raise RuntimeError("EPUB-fel: manifest/spine saknas.")

        nav_item = next(
            (item for item in manifest.findall("opf:item", ns)
             if "nav" in item.attrib.get("properties", "").split()),
            None,
        )
        if nav_item is None:
            raise RuntimeError("EPUB-fel: nav.xhtml saknas.")

        nav_path = (Path(opf_name).parent / nav_item.attrib["href"]).as_posix()
        nav_root = ET.fromstring(archive.read(nav_path))
        nav_ns = {"x": XHTML_NS, "epub": EPUB_NS}
        anchors = nav_root.findall(".//x:nav[@epub:type='toc']//x:a", nav_ns)
        labels = ["".join(anchor.itertext()).strip() for anchor in anchors]
        chapter_labels = [label for label in labels if re.match(r"^\d+\.\s", label)]
        if len(chapter_labels) != expected_chapters:
            raise RuntimeError(
                f"EPUB-fel: TOC har {len(chapter_labels)} kapitelposter, väntat {expected_chapters}."
            )
        if title in labels:
            raise RuntimeError("EPUB-fel: titelsidan finns felaktigt med i TOC.")

        nav_id = nav_item.attrib["id"]
        nav_refs = [
            ref for ref in spine.findall("opf:itemref", ns)
            if ref.attrib.get("idref") == nav_id
        ]
        if nav_refs and any(ref.attrib.get("linear") != "no" for ref in nav_refs):
            raise RuntimeError("EPUB-fel: nav.xhtml är linjär i spine.")

        split_headings = 0
        for name in names:
            if not name.endswith(".xhtml"):
                continue
            data = archive.read(name).decode("utf-8", errors="replace")
            if 'class="chapter-number"' in data and 'class="chapter-title"' in data:
                split_headings += 1
        if split_headings != expected_chapters:
            raise RuntimeError(
                f"EPUB-fel: {split_headings} formaterade kapitelrubriker, väntat {expected_chapters}."
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--formats", default="epub,pdf")
    parser.add_argument("--allow-pandoc-version-mismatch", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_dir = Path(args.output_dir).resolve()

    validation = subprocess.run([sys.executable, "scripts/validate_project.py", "."], cwd=root)
    if validation.returncode != 0:
        return validation.returncode

    version = pandoc_version()
    if version != PANDOC_VERSION and not args.allow_pandoc_version_mismatch:
        print(
            f"ERROR: Pandoc {PANDOC_VERSION} krävs för reproducerbart bygge; hittade {version}.",
            file=sys.stderr,
        )
        return 2

    metadata = simple_metadata(root / "publishing/metadata.yaml")
    title = metadata["title"]
    subtitle = metadata.get("subtitle", "")
    series = metadata.get("series", "")
    author = metadata["author"]
    base_name = args.name or slugify(title)
    formats = [x.strip().lower() for x in args.formats.split(",") if x.strip()]
    invalid = sorted(set(formats) - {"epub", "pdf"})
    if invalid or not formats:
        print("ERROR: --formats måste innehålla epub och/eller pdf.", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="roman-build-") as tmp:
        temp = Path(tmp)
        chapters = normalized_chapters(root, temp)
        if not chapters:
            print("ERROR: Inga kapitelfiler hittades.", file=sys.stderr)
            return 2

        if "epub" in formats:
            output = output_dir / f"{base_name}.epub"
            title_page = temp / "00-title.md"
            parts = ['<section class="title-page">']
            if series:
                parts.append(f'<p class="series">{series}</p>')
            parts.append(f'<p class="book-title">{title}</p>')
            if subtitle:
                parts.append(f'<p class="subtitle">{subtitle}</p>')
            parts.append(f'<p class="author">{author}</p>')
            parts.append('</section>')
            title_page.write_text("\n".join(parts) + "\n", encoding="utf-8")

            command = [
                "pandoc", str(title_page), *[str(p) for p in chapters],
                "--from=markdown+raw_html",
                "--to=epub3",
                "--output", str(output),
                "--metadata-file", str(root / "publishing/metadata.yaml"),
                "--css", str(root / "publishing/epub.css"),
                "--epub-cover-image", str(root / "omslag/cover.jpg"),
                "--epub-title-page=false",
                "--toc",
                "--toc-depth=1",
            ]
            subprocess.run(command, cwd=root, check=True)
            subprocess.run(
                [sys.executable, str(root / "publishing/fix-epub-after-pandoc.py"), str(output)],
                cwd=root,
                check=True,
            )
            validate_epub(output, len(chapters), title)
            print(f"OK: EPUB skapad och verifierad: {output}")

        if "pdf" in formats:
            pdf = output_dir / f"{base_name}.pdf"
            if shutil.which("xelatex") is None:
                print("ERROR: xelatex krävs för PDF-bygget.", file=sys.stderr)
                return 2

            required = [
                "texgyrepagella-regular.otf",
                "texgyrepagella-bold.otf",
                "texgyrepagella-italic.otf",
                "texgyrepagella-bolditalic.otf",
            ]
            font_dir = None
            for base in (Path("/usr/share/texmf"), Path("/usr/share/fonts")):
                if not base.exists():
                    continue
                for regular in base.rglob(required[0]):
                    candidate = regular.parent
                    if all((candidate / name).is_file() for name in required):
                        font_dir = candidate
                        break
                if font_dir:
                    break

            font_args = []
            if font_dir:
                font_args = ["--variable", f"pdf-font-dir={font_dir.as_posix()}"]

            command = [
                "pandoc", *[str(p) for p in chapters],
                "--from=markdown",
                "--to=pdf",
                "--pdf-engine=xelatex",
                "--output", str(pdf),
                "--metadata-file", str(root / "publishing/metadata.yaml"),
                "--template", str(root / "publishing/pdf-template.tex"),
                "--lua-filter", str(root / "publishing/pdf-filter.lua"),
                *font_args,
                "--top-level-division=chapter",
            ]
            subprocess.run(command, cwd=root, check=True)
            if not pdf.exists() or pdf.stat().st_size < 10_000:
                print("ERROR: PDF-bygget gav ingen giltig PDF-fil.", file=sys.stderr)
                return 2
            print(f"OK: PDF skapad: {pdf}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
