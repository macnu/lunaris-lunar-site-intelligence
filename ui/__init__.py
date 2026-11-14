"""Interfaz Streamlit de LSI. Solo ``app.py`` y ``ui/`` importan streamlit (RNF-09); la UI no calcula, llama a ``lsi.pipeline``.

Páginas en ``ui/pages/<nombre>.py``; ``discover_pages`` las descubre dinámicamente y tolera que falten.
"""
from __future__ import annotations

from pathlib import Path

# (fichero sin .py, título, icono Material) en el orden de navegación (arquitectura §11.2)
PAGE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("search", "Buscador", ":material/search:"),
    ("site_capacity", "Capacidad del sitio", ":material/satellite_alt:"),
    ("explorer", "Explorador 3D", ":material/terrain:"),
    ("best_spots", "Mejores puntos y fechas", ":material/event_available:"),
    ("horizon_visibility", "Horizonte y visibilidad", ":material/wb_twilight:"),
    ("timeline", "Línea temporal", ":material/timeline:"),
    ("comparison", "Comparación de sitios", ":material/compare_arrows:"),
    ("power_panels", "Potencia y paneles", ":material/solar_power:"),
    ("site_score", "Score del sitio", ":material/grade:"),
    ("about", "Acerca de y límites", ":material/info:"),
)


# Agrupación de la navegación superior (4 secciones). Cada página sigue siendo un fichero de ``ui/pages``.
NAV_SECTIONS: dict[str, str] = {
    "search": "Explorador", "explorer": "Explorador", "best_spots": "Explorador",
    "site_capacity": "Análisis", "horizon_visibility": "Análisis", "timeline": "Análisis", "power_panels": "Análisis",
    "site_score": "Análisis", "comparison": "Comparativa", "about": "Informe",
}


def discover_pages(pages_dir: Path) -> tuple[list[tuple[Path, str, str]], list[str]]:
    """Páginas existentes ``[(ruta, título, icono)]`` en el orden de ``PAGE_SPECS`` y nombres de las que faltan."""
    found, missing = [], []
    for name, title, icon in PAGE_SPECS:
        p = Path(pages_dir) / f"{name}.py"
        (found if p.is_file() else missing).append((p, title, icon) if p.is_file() else name)
    return found, missing
