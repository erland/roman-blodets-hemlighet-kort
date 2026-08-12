# Build notes

Markdown i `kapitel/kapitel-XX.md` är kanonisk romantext.

`kapitelnoteringar.md` och övriga projekt-/revisionsfiler exporteras aldrig.

## Automatiserat publiceringsflöde

- Validate: PR och push till `main`
- Build Preview: manuell `workflow_dispatch`
- Release: taggar som matchar `v*`
- Pandoc: låst till 3.1.11.1
- Preview-artifact: `blodets-hemlighet-preview`
- Preview innehåller EPUB och PDF i samma GitHub Actions-artifact
- Release publicerar EPUB och PDF som separata assets
- EPUB har navigerbar intern TOC men ingen synlig innehållsförteckningssida i läsflödet
- PDF följer referenskonceptets synliga innehållsförteckning
- Omslag: `omslag/cover.jpg`
