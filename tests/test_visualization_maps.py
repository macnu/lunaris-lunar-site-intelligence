"""Mapas del Explorador: superficie 3D (arreglo P1-1) y mapa topográfico 2D ``relief_map_figure``. Sin DEM real ni SPICE."""
import numpy as np
import plotly.graph_objects as go
import pytest

from lsi.contracts import DemLayer, DemWindow, HorizonMode, ObserverPoint
from lsi.visualization import relief_map as R, terrain3d as T

X0, Y0 = -3500.0, 122000.0     # lejos del origen, como en Malapert: es lo que rompía el 3D


def dem(n=40, px=40.0, nan=False):
    r, c = np.mgrid[0:n, 0:n]
    z = 3000.0 + 20.0 * c + 400.0 * np.exp(-((r - n / 2) ** 2 + (c - n / 2) ** 2) / 40.0)   # rampa + «cráter»
    if nan:
        z[0, :5] = np.nan
        z[n // 2, n // 2] = np.nan
    return DemWindow(z, X0, Y0, px, DemLayer.SURF)


def obs(win):
    return ObserverPoint(-85.98, 358.3, X0 + 800, Y0 - 800, 2.0, HorizonMode.DEM, ground_z_m=3500.0, label="Obs")


# ------------------------------------------------------------------ 3D
def test_3d_superficie_finita_sin_botones_y_en_km_locales():
    win = dem()
    fig = T.terrain_surface_3d(win, obs(win), layer="slope", buttons=False, markers=[("Sitio", X0 + 400, Y0 - 400, 3300.0)])
    surf = [t for t in fig.data if isinstance(t, go.Surface)]
    assert len(surf) == 1 and surf[0].name == "Pendiente"                  # solo la capa activa
    assert np.isfinite(np.asarray(surf[0].z)).all() and np.isfinite(np.asarray(surf[0].surfacecolor)).all()
    assert not fig.layout.updatemenus                                     # nada tapa el lienzo
    # causa raíz: x, y locales (≈ ±0,8 km), nunca los 122 000 m absolutos
    assert abs(np.asarray(surf[0].y)).max() < 2.0 and abs(np.asarray(surf[0].x)).max() < 2.0
    sc = fig.layout.scene
    assert sc.aspectmode == "manual" and sc.aspectratio.y == pytest.approx(1.0) and sc.aspectratio.z > 0
    assert list(sc.domain.x) == [0, 1] and "km" in sc.xaxis.title.text and "km" in sc.yaxis.title.text
    assert sc.xaxis.range is not None and sc.zaxis.range[0] < sc.zaxis.range[1]
    assert sc.camera.eye.z > 0 and any(t.name == "Observador" for t in fig.data)


def test_3d_camara_mira_desde_el_norte_y_exageracion_escala_z():
    win = dem()
    a = T.terrain_surface_3d(win, None, buttons=False, z_exaggeration=1.0)
    b = T.terrain_surface_3d(win, None, buttons=False, z_exaggeration=3.0)
    assert b.layout.scene.aspectratio.z == pytest.approx(3 * a.layout.scene.aspectratio.z)
    assert a.layout.scene.camera.eye.y > abs(a.layout.scene.camera.eye.x)   # +y = norte local con north_deg = 0


def test_3d_compatible_con_botones_y_tolera_nan():
    win = dem(nan=True)
    fig = T.terrain_surface_3d(win, None, buttons=True)
    assert len(fig.layout.updatemenus[0].buttons) == 2 and sum(t.visible for t in fig.data) == 1


# ------------------------------------------------------------------ 2D
def test_hillshade_independiente():
    c = np.arange(41, dtype=float)
    z = np.tile(5.0 * np.minimum(c, 40 - c), (41, 1))            # cresta N-S: ladera oeste sube al este, ladera este baja
    oeste, este = (slice(None), slice(5, 15)), (slice(None), slice(25, 35))
    sol_w = R.hillshade(z, 5.0, azimuth_deg=270.0, elevation_deg=30.0, exaggeration=1.0)
    sol_e = R.hillshade(z, 5.0, azimuth_deg=90.0, elevation_deg=30.0, exaggeration=1.0)
    # la ladera oeste mira al oeste: iluminada con el Sol en el oeste y en sombra con el Sol en el este (y al revés)
    assert sol_w[oeste].mean() > 0.9 and sol_w[este].mean() < 0.1
    assert sol_e[oeste].mean() < 0.1 and sol_e[este].mean() > 0.9
    assert np.nanmin(sol_w) >= 0.0 and np.nanmax(sol_w) <= 1.0


def test_relief_map_trae_hillshade_contornos_escala_y_norte():
    win = dem()
    fig = R.relief_map_figure(win, obs(win), candidates=[("A", X0 + 100, Y0 - 100), ("B", X0 + 900, Y0 - 900)],
                              labels=[("Lhamu", X0 + 600, Y0 - 600, "Crater", 1.0), ("Mons X", X0 + 300, Y0 - 1200, "Mons", None)],
                              north_deg=-1.7, selectable=True)
    names = [t.name for t in fig.data]
    assert "Relieve sombreado" in names and any(isinstance(t, go.Contour) for t in fig.data)
    assert "Escala" in names and any("km" in (a.text or "") for a in fig.layout.annotations)
    assert any("<b>N</b>" in (a.text or "") for a in fig.layout.annotations) and any(a.showarrow for a in fig.layout.annotations)
    assert "Observador" in names and "Candidatos" in names and "Nombres" in names and "clic" in names
    cand = next(t for t in fig.data if t.name == "Candidatos")
    assert list(cand.text) == ["1", "2"]
    nom = next(t for t in fig.data if t.name == "Nombres")
    assert list(nom.text) == ["Lhamu", "Mons X"] and nom.marker.symbol[0] != nom.marker.symbol[1]   # símbolo por tipo
    assert fig.layout.yaxis.scaleanchor == "x"


def test_relief_map_determinista_y_capas():
    win = dem()
    a = R.relief_map_figure(win, obs(win), layer="slope").to_json()
    assert a == R.relief_map_figure(win, obs(win), layer="slope").to_json()
    extra = {"uncertainty": np.ones(win.data.shape)}
    for k in ("elevation", "slope", "uncertainty", "sampling", "inexistente"):       # sampling sin dato → elevación
        assert len(R.relief_map_figure(win, layer=k, layers=extra).data) >= 2


def test_relief_map_tolera_nan_nodata_y_bordes():
    win = dem(nan=True)
    f = R.relief_map_figure(win, obs(win), labels=[("Fuera", 1e9, 1e9, "Crater", 3.0), ("Borde", X0, Y0, "Crater", 1.0)])
    assert list(next(t for t in f.data if t.name == "Nombres").text) == ["Borde"]     # fuera del recorte: ignorado
    shade = R.hillshade(win.data, win.pixel_size_m)
    assert np.isnan(shade[0, 0]) and np.isfinite(shade[20, 5])
    vacio = R.relief_map_figure(DemWindow(np.full((6, 6), np.nan), X0, Y0, 40.0, DemLayer.SURF))
    assert "Sin datos" in vacio.layout.annotations[0].text
    tira = R.relief_map_figure(DemWindow(np.linspace(0, 1, 7)[None, :], X0, Y0, 40.0, DemLayer.SURF))   # 1 × 7: sin gradiente
    assert len(tira.data) >= 2


def test_relief_map_compact_es_mas_pequeno():
    win = dem()
    big = R.relief_map_figure(win, obs(win), labels=[(f"n{i}", X0 + 100 * i, Y0 - 100 * i, "Crater", 1.0) for i in range(6)])
    small = R.relief_map_figure(win, obs(win), compact=True, labels=[(f"n{i}", X0 + 100 * i, Y0 - 100 * i, "Crater", 1.0) for i in range(6)])
    assert small.layout.height < big.layout.height <= 700
    assert small.layout.xaxis.visible is False and big.layout.xaxis.visible is not False
    assert not any(isinstance(t, go.Contour) for t in small.data)
    assert len(next(t for t in small.data if t.name == "Nombres").text) == 3
    assert not any(getattr(t, "showscale", False) for t in small.data if isinstance(t, go.Heatmap))


# ------------------------------------------------------------------ textura, iluminación y limpieza de rótulos
def test_3d_textura_horneada_iluminacion_nombres_y_observador_con_linea():
    win = dem()
    ill = np.ones(win.data.shape)
    ill[:, :20] = 0.0
    fig = T.terrain_surface_3d(win, obs(win), layer="illumination", buttons=False, illumination=ill, sun_az_deg=90.0, sun_el_deg=2.0,
                               labels=[("Cráter A", X0 + 800, Y0 - 800, "Crater", 3.0), ("Lejos", 9e9, 9e9, "Crater", 9.0)],
                               markers=[("Sitio (c)", X0 + 400, Y0 - 400, 3300.0)])
    surf = next(t for t in fig.data if isinstance(t, go.Surface))
    assert surf.name == "Iluminación" and len(surf.colorscale) <= 256 and not surf.contours.z.show
    sc = np.asarray(surf.surfacecolor)
    pal = [tuple(int(v) for v in c[1][4:-1].split(",")) for c in surf.colorscale]
    lit, dark = pal[int(sc[20, 30])], pal[int(sc[20, 3])]
    assert sum(dark) < sum(lit) / 3 and dark[2] > dark[0]                    # sombra azul muy oscura; iluminado cálido (R > B)
    assert lit[0] > lit[2]
    nombres = next(t for t in fig.data if t.name == "Nombres")
    assert list(nombres.text) == ["Cráter A"]                                # el de fuera del recorte se descarta
    assert any(t.mode == "lines" for t in fig.data if isinstance(t, go.Scatter3d))     # línea vertical del observador
    assert list(next(t for t in fig.data if t.name == "Candidatos").text) == ["1"]
    assert 25 <= np.degrees(np.arctan2(fig.layout.scene.camera.eye.z, np.hypot(fig.layout.scene.camera.eye.x, fig.layout.scene.camera.eye.y))) <= 35


def test_ticks_sin_cero_negativo():
    assert R.km_text(-0.0) == "0,0" and R.km_text(-20.0) == "0,0" and R.km_text(-1500.0) == "-1,5" and R.km_text(2000.0) == "2,0"
    win = dem()
    fig = R.relief_map_figure(win, obs(win))
    assert not any(t.startswith("-0") for t in fig.layout.xaxis.ticktext + fig.layout.yaxis.ticktext)
    t3 = T.terrain_surface_3d(win, None, buttons=False)
    assert not any(t.startswith("-0,0") for t in t3.layout.scene.xaxis.ticktext)


def test_mapa_2d_capa_iluminacion_y_rotulo_sin_jerga():
    win = dem()
    o = ObserverPoint(-85.98, 358.3, X0 + 800, Y0 - 800, 2.0, HorizonMode.DEM, ground_z_m=3500.0,
                      label="Site04 Shackleton rim [snap_to_dem: mejor punto, a 10.13 km del punto pedido]")
    ill = np.ones(win.data.shape)
    ill[:, :10] = 0.0
    fig = R.relief_map_figure(win, o, layer="illumination", illumination=ill, sun_azimuth_deg=90.0, sun_elevation_deg=2.0,
                              observer_subtitle="mejor punto dentro del cráter, a 0,12 km del centro")
    assert [t.name for t in fig.data if isinstance(t, go.Heatmap)][-2:] == ["Iluminado", "En sombra"]
    textos = " ".join(a.text or "" for a in fig.layout.annotations)
    assert "iluminado" in textos and "en sombra" in textos and "Site04 Shackleton rim" in textos and "mejor punto dentro del cráter" in textos
    assert "snap_to_dem" not in textos and "snap_to_dem" not in json_text(fig)
    sin = R.relief_map_figure(win, o, layer="illumination")                    # sin fracción: cae a la elevación
    assert not any(t.name == "Iluminado" for t in sin.data)


def json_text(fig) -> str:
    return " ".join(str(getattr(t, "text", "")) + str(getattr(t, "hovertemplate", "")) for t in fig.data)
