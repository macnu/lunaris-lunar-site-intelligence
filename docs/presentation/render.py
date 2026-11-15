# Renders presentation-en.html to PDF (7 slides, 16:9) with Playwright + Chrome.
import pathlib
from playwright.sync_api import sync_playwright
d = pathlib.Path(__file__).parent
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1600, "height": 900})
    pg.goto((d / "presentation-en.html").as_uri())
    pg.pdf(path=str(d / "lunaris-presentation-en.pdf"), width="1600px", height="900px", print_background=True, prefer_css_page_size=True)
    b.close()
