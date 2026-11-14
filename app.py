"""Lunar Site Intelligence (LSI): punto de entrada de Streamlit (``streamlit run app.py``).

Navegación con ``st.navigation`` sobre los ficheros de ``ui/pages/`` que existan (ver ``ui.PAGE_SPECS``); si falta alguno
o todos, la app arranca igual con un aviso amable. ``LSI_PAGES_DIR`` permite apuntar a otra carpeta (pruebas).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "src")):     # `ui` y `lsi` importables aunque no estén instalados
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st  # noqa: E402

from lsi.contracts import LSIError  # noqa: E402
from ui import PAGE_SPECS, discover_pages  # noqa: E402

st.set_page_config(page_title="Lunar Site Intelligence", page_icon=":material/dark_mode:", layout="wide",
                   initial_sidebar_state="expanded")

from ui import cache, components as C, sidebar, state  # noqa: E402


def _home() -> None:
    st.title("Lunar Site Intelligence")
    st.markdown("Compara emplazamientos del polo sur lunar y fechas: horizonte, Sol y Tierra, potencia de paneles y score.")
    st.info("Todavía no hay páginas disponibles en `ui/pages/`. La barra lateral ya funciona; "
            "las pantallas aparecerán aquí en cuanto existan.", icon=":material/construction:")
    C.warnings_band()


def main() -> None:
    C.inject_styles()
    try:
        ctx = cache.get_context()
    except LSIError as e:       # p. ej. KernelsMissingError (arquitectura §9.1): pantalla de configuración
        st.title("Lunar Site Intelligence")
        C.show_error(e)
        st.code("python scripts/fetch_data.py", language="bash")
        st.stop()
        return
    state.init_state(ctx)
    sidebar.render_sidebar(ctx)

    pages_dir = Path(os.environ.get("LSI_PAGES_DIR", ROOT / "ui" / "pages"))
    found, missing = discover_pages(pages_dir)
    pages = [st.Page(str(path), title=title, icon=icon, url_path=path.stem) for path, title, icon in found]
    if not pages:
        pages = [st.Page(_home, title="Inicio", icon=":material/home:", url_path="inicio", default=True)]
    elif missing:
        title = {n: t for n, t, _ in PAGE_SPECS}
        st.sidebar.caption("Páginas pendientes: " + ", ".join(title[n] for n in missing))
    st.navigation(pages).run()


main()
