# NASA Space Apps 2026 — submission text (English draft)

Challenge: **Lunar Landing Site Navigator**. Project: **Lunar Site Intelligence (LSI) / LUNARIS**.
Draft for the owner to review and paste into the Project tab. The portal requires English, a public demo link
(video ≤ 30 s or ≤ 7 slides — confirm in the 2026 Project Submission Guide), AI-tool disclosure and references.

## Short description

LSI answers one question for any point near the lunar south pole and any date: **does this spot see the Sun,
does it see the Earth, and could it actually talk to it?** It combines real NASA data (LOLA elevation models,
SPICE ephemerides, Deep Space Network station geometry with local time) to compute solar capacity, line-of-sight
communication continuity and a suitability verdict per mission window, and shows it with maps and a 3D viewer
(real LROC photo, Sun and Earth in their true positions, an observer's-eye view).

What makes it different from existing viewers: the same site with the same sunlight can be **APTO (97.4)** or
**CONDICIONAL (73.9)** depending on the start date, because Earth visibility is treated as continuity of the link
(longest gap without contact), not as a single yes/no. Bad results are published on purpose, and the error of
the coarse far-field mode is stated on screen. Top-ranked spots are labelled **candidates**, not certified sites:
they do not match the published illumination map to within ±0.2–0.3.

## Demo

`demo_out/lsi-demo-en-30s.mp4` (28.6 s, English voice-over; the on-screen interface is in Spanish). Not yet uploaded:
the owner must host it (YouTube or Google Drive) with a public link and paste it in the Project tab.

## How to try it

Python 3.11. `pip install -r requirements.txt`, download data with the scripts in `scripts/`, then
`python -m streamlit run app.py`. Code licence: Apache-2.0 (`LICENSE`). Data keep their own licences and citations.
Full method, validation and declared limits: `README.md`, `docs/metodologia.md`, `docs/limitaciones.md`
(in Spanish).

## Use of AI tools (required disclosure)

The software was written with **Claude Code (Anthropic, Claude Sonnet 5.5)** as a coding assistant over the
hackathon weekend (14–15 Nov 2026), directed by the team. Claude Code wrote and refactored code, tests and
documentation, ran the test suite (997 tests), recorded the demo with a scripted browser and a Windows
text-to-speech voice, and ran simulated review panels used to find weaknesses. Scientific numbers come from
the NASA data and the code, not from the model; figures in the demo are read from the screen by the script.
The team decided scope, priorities and what to claim, and is responsible for the content.

## References / data sources

- LOLA 5 m south-polar site DEMs, PGDA product 78 (Mazarico et al. 2011; Barker et al. 2021), https://pgda.gsfc.nasa.gov/products/78
- LOLA 80 m south-polar DEM, PGDA product 90, https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF
- SPICE kernels, NASA NAIF, https://naif.jpl.nasa.gov/pub/naif/generic_kernels/ (usage rules: https://naif.jpl.nasa.gov/naif/rules.html)
- JPL Horizons, used as independent check of Sun/Earth geometry
- DSN station coordinates and elevation conventions: DSN 810-005 / 301 (Rev. P)
- Gazetteer of Planetary Nomenclature (USGS / IAU WGSN), https://planetarynames.wr.usgs.gov/
- LROC NAC imagery and SDEM orthomosaic (Bertone et al. 2025), Diviner thermal maps, PSR maps and the published
  illumination map: exact products, versions and licence status in `docs/fuentes-datos.md`
- three.js (vendored with its licence), Streamlit

Nothing here uses the NASA logo.
