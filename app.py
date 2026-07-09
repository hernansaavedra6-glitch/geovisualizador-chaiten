"""
GeoVisualizador Web - Riesgo volcánico y territorio, Chaitén
Trabajo Final - Curso Aplicaciones SIG, UACh
Autor: Hernán Saavedra Ruiz
"""

import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import rasterio
import folium
from folium import plugins
from folium import LayerControl
from streamlit_folium import st_folium
import plotly.express as px
import matplotlib as mpl
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from pathlib import Path
import shapely.geometry
import branca.colormap as bcm

# Configuración de página ancha
st.set_page_config(page_title="GeoVisualizador Chaitén", layout="wide", page_icon="🌋")

DATA_DIR = Path(__file__).parent / "data"

# ----------------------------------------------------------------------
# CARGA DE DATOS
# ----------------------------------------------------------------------
@st.cache_data
def cargar_vector(nombre_archivo):
    path = DATA_DIR / nombre_archivo
    if not path.exists(): return None
    try:
        gdf = gpd.read_file(path)
        gdf = gdf.dropna(subset=['geometry']) 
        if gdf.crs is None: gdf = gdf.set_crs("EPSG:4326")
        else: gdf = gdf.to_crs("EPSG:4326")
        gdf.geometry = gdf.geometry.simplify(0.0005)
        return gdf
    except Exception: return None

limite = cargar_vector("limite_chaiten.shp")
pumalin = cargar_vector("parque_pumalin.shp")
hidrografia = cargar_vector("hidrografia.shp")
amenaza = cargar_vector("amenaza_volcanica.shp") 
volcan = cargar_vector("volcan_chaiten.shp")
red_vial = cargar_vector("red_vial.shp")

# CARGA DEM
dem_data, dem_bounds_latlon, vmin, vmax = (None, None, None, None)
try:
    with rasterio.open(DATA_DIR / "dem_chaiten.tif") as src:
        dem_data_raw = src.read(1).astype(float)
        stride = max(1, dem_data_raw.shape[0] // 800)
        dem_data = dem_data_raw[::stride, ::stride]
        if src.nodata is not None: dem_data = np.where(dem_data == src.nodata, np.nan, dem_data)
        vmin, vmax = float(np.nanmin(dem_data)), float(np.nanmax(dem_data))
        bbox = shapely.geometry.box(*src.bounds)
        gdf_bbox = gpd.GeoDataFrame({'geometry': [bbox]}, crs=src.crs).to_crs("EPSG:4326")
        b = gdf_bbox.total_bounds 
        dem_bounds_latlon = [[b[1], b[0]], [b[3], b[2]]]
except Exception: dem_data = None

# ----------------------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------------------
st.sidebar.title("🌋 GeoVisualizador Chaitén")
mostrar_limite = st.sidebar.checkbox("Límite comunal", True)
mostrar_amenaza = st.sidebar.checkbox("Zonas de amenaza volcánica", True)
mostrar_vial = st.sidebar.checkbox("Red Vial", True)
mostrar_hidro = st.sidebar.checkbox("Hidrografía", True)
mostrar_pumalin = st.sidebar.checkbox("Parque Nacional Pumalín", True)
mostrar_dem = st.sidebar.checkbox("DEM (Relieve base)", False)
mapa_base = st.sidebar.selectbox("Estilo:", ["CartoDB Positron", "OpenStreetMap", "Satélite (Esri)"])

# ----------------------------------------------------------------------
# MAPA E INTERFAZ
# ----------------------------------------------------------------------
st.title("GeoVisualizador — Exposición Territorial Chaitén")
m = folium.Map(location=[-42.85, -72.70], zoom_start=9, tiles="CartoDB positron")

if mostrar_dem and dem_data is not None:
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    dem_norm_safe = np.nan_to_num((dem_data - vmin) / (vmax - vmin), nan=0.0)
    cmap = mpl.colormaps['terrain'] 
    rgba = (cmap(dem_norm_safe) * 255).astype(np.uint8)
    rgba[np.isnan(dem_data), 3] = 0
    folium.raster_layers.ImageOverlay(image=rgba, bounds=dem_bounds_latlon, name="DEM", opacity=0.6).add_to(m)

# AMENAZA
if mostrar_amenaza and amenaza is not None:
    for _, row in amenaza.iterrows():
        folium.GeoJson(row.geometry, style_function=lambda x: {"color": "#b30000", "fillOpacity": 0.4}).add_to(m)

# OTRAS CAPAS
if mostrar_hidro and hidrografia is not None:
    folium.GeoJson(hidrografia, style_function=lambda x: {"color": "#08519c"}).add_to(m)

if mostrar_vial and red_vial is not None:
    folium.GeoJson(red_vial, style_function=lambda x: {"color": "#4d4d4d"}).add_to(m)

LayerControl().add_to(m)
st_folium(m, width=None, height=600)

# ESTADÍSTICAS
st.subheader("📊 Distribución del Riesgo")
if amenaza is not None:
    df_chart = amenaza.copy()
    df_chart["area_km2"] = df_chart.to_crs("EPSG:32718").geometry.area / 1e6
    fig = px.pie(df_chart, names=amenaza.columns[0], values="area_km2")
    st.plotly_chart(fig)
