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
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from pathlib import Path
import shapely.geometry
import branca.colormap as bcm

st.set_page_config(page_title="GeoVisualizador Chaitén", layout="wide", page_icon="🌋")

DATA_DIR = Path(__file__).parent / "data"

# ----------------------------------------------------------------------
# CARGA DE DATOS SEGUROS
# ----------------------------------------------------------------------
@st.cache_data
def cargar_vector(nombre_archivo):
    path = DATA_DIR / nombre_archivo
    if not path.exists():
        return None
    try:
        gdf = gpd.read_file(path)
        gdf = gdf.dropna(subset=['geometry']) # Limpieza anti-corrupción
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        else:
            gdf = gdf.to_crs("EPSG:4326")
        return gdf
    except Exception:
        return None

limite = cargar_vector("limite_chaiten.shp")
pumalin = cargar_vector("parque_pumalin.shp")
hidrografia = cargar_vector("hidrografia.shp")
amenaza = cargar_vector("amenaza_volcanica.shp")  # generado por generar_amenaza_volcanica.py (cost-distance real, no círculos)
volcan = cargar_vector("volcan_chaiten.shp")

for _nombre, _gdf, _archivo in [
    ("Límite comunal", limite, "limite_chaiten.shp"),
    ("Parque Pumalín", pumalin, "parque_pumalin.shp"),
    ("Hidrografía", hidrografia, "hidrografia.shp"),
    ("Zonas de amenaza", amenaza, "amenaza_volcanica.shp"),
    ("Volcán (punto)", volcan, "volcan_chaiten.shp"),
]:
    if _gdf is None:
        st.sidebar.warning(f"⚠️ No se pudo cargar '{_archivo}' ({_nombre}). Revisa que exista en data/.")
    elif len(_gdf) == 0:
        st.sidebar.warning(f"⚠️ '{_archivo}' ({_nombre}) se cargó pero está vacío (0 geometrías).")

# --- CARGA DEL DEM CON REPROYECCIÓN DE LÍMITES ---
dem_data, dem_bounds_latlon, vmin, vmax = (None, None, None, None)
try:
    with rasterio.open(DATA_DIR / "dem_chaiten.tif") as src:
        dem_data = src.read(1).astype(float)
        if src.nodata is not None:
            dem_data = np.where(dem_data == src.nodata, np.nan, dem_data)
        vmin, vmax = float(np.nanmin(dem_data)), float(np.nanmax(dem_data))
        
        # Truco experto: Convertir los límites del raster (UTM) a Lat/Lon para Folium
        bbox = shapely.geometry.box(*src.bounds)
        gdf_bbox = gpd.GeoDataFrame({'geometry': [bbox]}, crs=src.crs).to_crs("EPSG:4326")
        b = gdf_bbox.total_bounds # [lon_min, lat_min, lon_max, lat_max]
        dem_bounds_latlon = [[b[1], b[0]], [b[3], b[2]]]
except Exception as e:
    dem_data = None

# ----------------------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------------------
st.sidebar.title("🌋 GeoVisualizador Chaitén")
st.sidebar.markdown("**Riesgo volcánico, hidrografía y territorio**")
st.sidebar.markdown("---")

st.sidebar.subheader("Capas Principales")
mostrar_limite = st.sidebar.checkbox("Límite comunal", value=True)
mostrar_amenaza = st.sidebar.checkbox("Zonas de amenaza volcánica", value=True)
mostrar_hidro = st.sidebar.checkbox("Hidrografía", value=True)
mostrar_pumalin = st.sidebar.checkbox("Parque Nacional Pumalín", value=True)
mostrar_dem = st.sidebar.checkbox("DEM (Relieve base)", value=False)

st.sidebar.markdown("---")
st.sidebar.subheader("🗺️ Opciones de Mapa Base")
# Dejamos CartoDB primero para la estética pro
mapa_base = st.sidebar.selectbox("Selecciona el estilo:", ["CartoDB Positron", "OpenStreetMap", "Satélite (Esri)"])

st.sidebar.markdown("---")
st.sidebar.subheader("📊 Estadísticas Dinámicas")
capa_stats = st.sidebar.selectbox("Ver estadísticas de:", ["Zonas de amenaza", "Hidrografía", "Parque Pumalín"])

def area_km2(gdf):
    return gdf.to_crs("EPSG:32718").geometry.area.sum() / 1e6

def largo_km(gdf):
    return gdf.to_crs("EPSG:32718").geometry.length.sum() / 1000

if capa_stats == "Zonas de amenaza" and amenaza is not None:
    st.sidebar.metric("Área total en riesgo", f"{area_km2(amenaza):.2f} km²")
elif capa_stats == "Hidrografía" and hidrografia is not None:
    st.sidebar.metric("Largo total red hídrica", f"{largo_km(hidrografia):.2f} km")
elif capa_stats == "Parque Pumalín" and pumalin is not None:
    st.sidebar.metric("Área Protegida", f"{area_km2(pumalin):.2f} km²")

# ----------------------------------------------------------------------
# MAPA PRINCIPAL
# ----------------------------------------------------------------------
st.title("GeoVisualizador — Exposición Territorial Chaitén")
st.markdown("Plataforma interactiva para el análisis de riesgo continuo (multiamenaza) del volcán Chaitén, integrando variables topográficas, hidrológicas y de conservación.")

tiles_dict = {"OpenStreetMap": "OpenStreetMap", "CartoDB Positron": "CartoDB positron", "Satélite (Esri)": None}
center = [-42.85, -72.70]
m = folium.Map(location=center, zoom_start=10, tiles=tiles_dict[mapa_base] if tiles_dict[mapa_base] else "OpenStreetMap")

# Centra y ajusta el zoom automáticamente al límite comunal real (más profesional
# que dejar siempre el mismo centro/zoom fijo, y evita que la app "empiece" mostrando el mar)
if limite is not None and len(limite) > 0:
    b = limite.total_bounds  # [minx, miny, maxx, maxy] en lon/lat
    m.fit_bounds([[b[1], b[0]], [b[3], b[2]]])

if mapa_base == "Satélite (Esri)":
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Satélite (Esri)", overlay=False, control=False,
    ).add_to(m)

# --- PLUGINS AVANZADOS (EL TOQUE 7.0) ---
plugins.Fullscreen(position='topleft', title="Pantalla Completa", title_cancel="Salir").add_to(m)
plugins.MeasureControl(position='topleft', primary_length_unit='kilometers', primary_area_unit='sqmeters').add_to(m)
plugins.MiniMap(toggle_display=True, position='bottomright').add_to(m)

# --- DEM (raster continuo) ---
if mostrar_dem and dem_data is not None and dem_bounds_latlon is not None:
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap = cm.get_cmap("terrain")
    rgba = (cmap(norm(dem_data)) * 255).astype(np.uint8)
    rgba[np.isnan(dem_data)] = [0, 0, 0, 0] # Transparencia a valores nulos
    
    folium.raster_layers.ImageOverlay(
        image=rgba, bounds=dem_bounds_latlon, name="DEM (elevación)", opacity=0.6,
    ).add_to(m)
    
    colormap = bcm.LinearColormap(
        colors=['#33a02c', '#b2df8a', '#fdbf6f', '#ff7f00', '#cab2d6', '#ffffff'], 
        vmin=vmin, vmax=vmax, caption="Elevación DEM (m.s.n.m)"
    )
    m.add_child(colormap)
elif mostrar_dem and dem_data is None:
    st.warning("⚠️ No se pudo cargar el archivo DEM. Verifica que 'dem_chaiten.tif' esté en la carpeta data.")

# --- Límite comunal ---
if mostrar_limite and limite is not None:
    _campos_limite = [c for c in limite.columns if c != "geometry"][:3]
    folium.GeoJson(
        limite, name="Límite comunal",
        style_function=lambda x: {"color": "#333333", "weight": 2, "fillOpacity": 0, "dashArray": "5,5"},
        tooltip=folium.GeoJsonTooltip(fields=_campos_limite) if _campos_limite else None,
    ).add_to(m)

# --- Parque Pumalín ---
# ¡AQUÍ ESTÁ EL ARREGLO FINAL!
if mostrar_pumalin and pumalin is not None:
    folium.GeoJson(
        pumalin, name="Parque Nacional Pumalín",
        style_function=lambda x: {"color": "#984ea3", "fillColor": "#984ea3", "weight": 3, "fillOpacity": 0.35},
        tooltip="Parque Nacional Pumalín"
    ).add_to(m)

# --- Hidrografía ---
if mostrar_hidro and hidrografia is not None:
    cols_disponibles = [c for c in hidrografia.columns if c != "geometry"]
    tipo_col = next((c for c in hidrografia.columns if c.lower() in ("tipo", "type", "clase")), None)
    campos_tooltip = [c for c in ["nombre", "NOMBRE", "tipo", "TIPO"] if c in hidrografia.columns]
    if len(campos_tooltip) < 2:
        # si no existen esos nombres exactos, usa las primeras columnas reales disponibles
        campos_tooltip = cols_disponibles[:2] if len(cols_disponibles) >= 2 else cols_disponibles

    def _estilo_hidro(feature):
        val = str(feature["properties"].get(tipo_col, "")).lower() if tipo_col else ""
        es_principal = any(k in val for k in ["rio", "río", "principal"])
        return {"color": "#08519c" if es_principal else "#6baed6", "weight": 3.5 if es_principal else 1.8}

    folium.GeoJson(
        hidrografia, name="Red Hídrica",
        style_function=_estilo_hidro,
        tooltip=folium.GeoJsonTooltip(fields=campos_tooltip) if campos_tooltip else None,
    ).add_to(m)

# --- Zonas de amenaza volcánica ---
colores_amenaza = {"Alto": "#d73027", "Moderado": "#fc8d59", "Bajo": "#fee08b"}
if mostrar_amenaza and amenaza is not None:
    col_nivel = "nivel" if "nivel" in amenaza.columns else amenaza.columns[0]
    fg_amenaza = folium.FeatureGroup(name="Zonas de Amenaza")
    for _, row in amenaza.sort_values(col_nivel, key=lambda s: s.map({"Bajo": 0, "Moderado": 1, "Alto": 2}).fillna(0)).iterrows():
        color = colores_amenaza.get(row[col_nivel], "#999999")
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda x, c=color: {"color": c, "fillColor": c, "weight": 1.5, "fillOpacity": 0.45},
            tooltip=f"Peligro: {row[col_nivel]} | Área: {row.get('area_km2', 0):.1f} km²", 
        ).add_to(fg_amenaza)
    fg_amenaza.add_to(m)

if mostrar_amenaza and volcan is not None:
    for _, row in volcan.iterrows():
        folium.Marker(
            [row.geometry.y, row.geometry.x], popup="Volcán Chaitén", tooltip="Cráter Volcán Chaitén",
            icon=folium.Icon(color="darkred", icon="fire", prefix="fa"),
        ).add_to(m)

# --- Leyenda ---
if mostrar_amenaza:
    leyenda_html = """
    <div style="position: fixed; bottom: 50px; left: 50px; z-index: 9999;
                background-color: rgba(255, 255, 255, 0.9); color: black; padding: 12px; border-radius: 8px;
                border: 2px solid rgba(0,0,0,0.2); font-size: 14px; box-shadow: 3px 3px 10px rgba(0,0,0,0.3);">
    <b style="color: black; font-size: 15px;">Nivel de Amenaza</b><br>
    <hr style="margin: 4px 0;">
    <span style="background:#d73027;width:14px;height:14px;display:inline-block;margin-right:8px;border-radius:50%;"></span><span style="color: black;">Alto</span><br>
    <span style="background:#fc8d59;width:14px;height:14px;display:inline-block;margin-right:8px;border-radius:50%;"></span><span style="color: black;">Moderado</span><br>
    <span style="background:#fee08b;width:14px;height:14px;display:inline-block;margin-right:8px;border-radius:50%;"></span><span style="color: black;">Bajo</span>
    </div>
    """
    m.get_root().html.add_child(folium.Element(leyenda_html))

LayerControl(collapsed=False).add_to(m)
st_data = st_folium(m, width=None, height=600)

# ----------------------------------------------------------------------
# GRÁFICOS Y TABLAS (Avance Rúbrica)
# ----------------------------------------------------------------------
st.markdown("---")
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📊 Distribución del Riesgo")
    if amenaza is not None:
        col_nivel = "nivel" if "nivel" in amenaza.columns else amenaza.columns[0]
        df_chart = amenaza.copy()
        df_chart["area_km2"] = df_chart.to_crs("EPSG:32718").geometry.area / 1e6
        fig = px.pie(
            df_chart, names=col_nivel, values="area_km2", 
            color=col_nivel, color_discrete_map=colores_amenaza,
            hole=0.4
        )
        fig.update_layout(height=350, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("📋 Explorador de Datos Espaciales")
    capa_tabla = st.selectbox("Capa a inspeccionar:", ["Zonas de amenaza", "Hidrografía", "Parque Pumalín", "Límite comunal"])
    gdf_map = {"Zonas de amenaza": amenaza, "Hidrografía": hidrografia, "Parque Pumalín": pumalin, "Límite comunal": limite}
    gdf_sel = gdf_map[capa_tabla]
    
    if gdf_sel is not None:
        df_show = gdf_sel.drop(columns="geometry")
        st.dataframe(df_show, use_container_width=True, height=250)
        st.download_button(
            label=f"⬇️ Descargar {capa_tabla} (GeoJSON)",
            data=gdf_sel.to_json(), file_name=f"{capa_tabla.lower().replace(' ', '_')}.geojson", mime="application/geo+json",
        )
    else:
        st.info("Archivo no disponible. Verifica que la capa exista en la carpeta data.")
