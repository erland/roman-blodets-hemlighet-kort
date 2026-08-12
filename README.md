# Romanprojekt

## Blodets hemlighet — Den första gnistan

Författare: Erland Lindmark

Detta projektarkiv innehåller planering, kontinuitet och kapitel för romanserien.

## Rekommenderat arbetsflöde

1. Följ kapitelplanen.
2. Skriv och revidera ett kapitel i taget.
3. Uppdatera kontinuitetsanteckningar och tidslinje efter varje godkänt kapitel.
4. Exportera EPUB/PDF när romanen är färdig.

## Projektstatus

- Fas: Planering klar / Kapitelproduktion ej påbörjad
- Omslagsbild: Planerad
- Senaste kapitel: Inga ännu


## GitHub Actions och publicering

Projektet innehåller nu ett reproducerbart publiceringsflöde:

- `.github/workflows/01-validate.yml`: validerar projektet på pull requests och push till `main`.
- `.github/workflows/02-build-preview.yml`: manuell preview som bygger EPUB + PDF och laddar upp ett gemensamt artifact `blodets-hemlighet-preview`.
- `.github/workflows/03-release.yml`: bygger EPUB + PDF på taggar `v*` och publicerar dem som separata GitHub Release-assets.
- `scripts/validate_project.py`: kontrollerar 12 kapitel, kapitelrubriker, metadata, arbetsmarkörer och interna Markdown-länkar.
- `scripts/build_book.py`: bygger från endast `kapitel/kapitel-XX.md`.
- `publishing/`: metadata, EPUB-layout, EPUB-efterbearbetning samt PDF-mall/filter.

`.github/` ligger i projektroten på samma nivå som denna `README.md`.

Kapitelnoteringar och projektanteckningar exporteras inte.
