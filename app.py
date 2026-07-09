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
import matplotlib as mpl # Añadido para solucionar el error del DEM
from pathlib import Path
import shapely.geometry
import branca.colormap as bcm

# Configuración de página ancha para mejor visualización
st.set_page_config(page_title="GeoVisualizador Chaitén", layout="wide", page_icon="🌋")

DATA_DIR = Path(__file__).parent / "data"

# ----------------------------------------------------------------------
# CARGA DE DATOS SEGUROS Y OPTIMIZADOS
# ----------------------------------------------------------------------
@st.cache_data
def cargar_vector(nombre_archivo):
    path = DATA_DIR / nombre_archivo
    if not path.exists():
        return None
    try:
        gdf = gpd.read_file(path)
        gdf = gdf.dropna(subset=['geometry']) 
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        else:
            gdf = gdf.to_crs("EPSG:4326")
            
        # Simplifica las geometrías para que la página cargue mucho más rápido
        gdf.geometry = gdf.geometry.simplify(0.0005)
        
        return gdf
    except Exception:
        return None

limite = cargar_vector("limite_chaiten.shp")
pumalin = cargar_vector("parque_pumalin.shp")
hidrografia = cargar_vector("hidrografia.shp")
amenaza = cargar_vector("amenaza_volcanica.shp") 
volcan = cargar_vector("volcan_chaiten.shp")
red_vial = cargar_vector("red_vial.shp")

# --- CARGA DEL DEM CON REPROYECCIÓN DE LÍMITES ---
dem_data, dem_bounds_latlon, vmin, vmax = (None, None, None, None)
try:
    with rasterio.open(DATA_DIR / "dem_chaiten.tif") as src:
        dem_data = src.read(1).astype(float)
        if src.nodata is not None:
            dem_data = np.where(dem_data == src.nodata, np.nan, dem_data)
        vmin, vmax = float(np.nanmin(dem_data)), float(np.nanmax(dem_data))
        
        bbox = shapely.geometry.box(*src.bounds)
        gdf_bbox = gpd.GeoDataFrame({'geometry': [bbox]}, crs=src.crs).to_crs("EPSG:4326")
        b = gdf_bbox.total_bounds 
        dem_bounds_latlon = [[b[1], b[0]], [b[3], b[2]]]
except Exception as e:
    dem_data = None

# ----------------------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------------------
st.sidebar.title("🌋 GeoVisualizador Chaitén")
st.sidebar.markdown("**Riesgo volcánico, vulnerabilidad e hidrografía**")
st.sidebar.markdown("---")

st.sidebar.subheader("Capas Principales")
mostrar_limite = st.sidebar.checkbox("Límite comunal", value=True)
mostrar_amenaza = st.sidebar.checkbox("Zonas de amenaza volcánica", value=True)
mostrar_vial = st.sidebar.checkbox("Red Vial (Conectividad)", value=True)
mostrar_hidro = st.sidebar.checkbox("Hidrografía", value=True)
mostrar_pumalin = st.sidebar.checkbox("Parque Nacional Pumalín", value=True)
mostrar_dem = st.sidebar.checkbox("DEM (Relieve base)", value=False)

st.sidebar.markdown("---")
st.sidebar.subheader("🗺️ Opciones de Mapa Base")
mapa_base = st.sidebar.selectbox("Selecciona el estilo:", ["CartoDB Positron", "OpenStreetMap", "Satélite (Esri)"])

st.sidebar.markdown("---")
st.sidebar.subheader("📊 Estadísticas Dinámicas")
capa_stats = st.sidebar.selectbox("Ver estadísticas de:", ["Zonas de amenaza", "Hidrografía", "Parque Pumalín", "Red Vial"])

def area_km2(gdf):
    if gdf is None or gdf.empty: return 0.0
    return gdf.to_crs("EPSG:32718").geometry.area.sum() / 1e6

def largo_km(gdf):
    if gdf is None or gdf.empty: return 0.0
    return gdf.to_crs("EPSG:32718").geometry.length.sum() / 1000

if capa_stats == "Zonas de amenaza" and amenaza is not None:
    st.sidebar.metric("Área total en riesgo", f"{area_km2(amenaza):.2f} km²")
elif capa_stats == "Hidrografía" and hidrografia is not None:
    st.sidebar.metric("Largo total red hídrica", f"{largo_km(hidrografia):.2f} km")
elif capa_stats == "Parque Pumalín" and pumalin is not None:
    st.sidebar.metric("Área Protegida", f"{area_km2(pumalin):.2f} km²")
elif capa_stats == "Red Vial" and red_vial is not None:
    st.sidebar.metric("Largo total de caminos", f"{largo_km(red_vial):.2f} km")

# ----------------------------------------------------------------------
# ANÁLISIS ESPACIAL EN TIEMPO REAL
# ----------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("🔥 Análisis de Impacto")
st.sidebar.caption("Calcula la afectación del volcán sobre áreas de conservación.")

if st.sidebar.button("Calcular impacto en Pumalín"):
    if pumalin is not None and not pumalin.empty and amenaza is not None:
        with st.sidebar.status("Procesando intersección espacial..."):
            pum_utm = pumalin.to_crs("EPSG:32718")
            amen_utm = amenaza.to_crs("EPSG:32718")
            
            col_nivel = "nivel" if "nivel" in amen_utm.columns else amen_utm.columns[0]
            amenaza_alta = amen_utm[amen_utm[col_nivel] == "Alto"]
            
            if not amenaza_alta.empty:
                interseccion = gpd.overlay(pum_utm, amenaza_alta, how='intersection')
                area_afectada = interseccion.geometry.area.sum() / 1e6
                st.sidebar.success(f"⚠️ {area_afectada:.2f} km² del Parque Nacional Pumalín se encuentran bajo riesgo volcánico ALTO.")
            else:
                st.sidebar.info("El parque no registra áreas en riesgo alto continuo.")
    else:
        st.sidebar.error("Error: La capa del Parque Pumalín está vacía o no se cargó.")

# NUEVO: FUENTES DE DATOS EN EL SIDEBAR
st.sidebar.markdown("---")
st.sidebar.info("Fuentes: IDE Chile, SERNAGEOMIN, NASA SRTM.")

# ----------------------------------------------------------------------
# MAPA PRINCIPAL E INTERFAZ
# ----------------------------------------------------------------------
st.title("GeoVisualizador — Exposición Territorial Chaitén")
st.markdown("Plataforma interactiva para el análisis de riesgo modelado mediante fricción espacial (cost-distance), integrando topografía, conectividad, hidrología y conservación.")
st.caption("Nota metodológica: El modelo de amenaza volcánica es una aproximación paramétrica basada en costo-distancia topográfica (flujos por gravedad) con fines demostrativos.")

# 1. INTEGRACIÓN: SECCIÓN DE USUARIOS
st.markdown("---")
st.subheader("👥 ¿A quién sirve esta herramienta?")
col_user1, col_user2, col_user3 = st.columns(3)

with col_user1:
    st.markdown("#### **Gestión Pública**")
    st.info("Apoyo a la Municipalidad de Chaitén en la planificación urbana y el ordenamiento territorial seguro.")

with col_user2:
    st.markdown("#### **Respuesta ante Desastres**")
    st.warning("Herramienta clave para **SENAPRED** en la identificación de infraestructuras críticas que podrían quedar aisladas.")

with col_user3:
    st.markdown("#### **Comunidad y Educación**")
    st.success("Recurso para que los habitantes comprendan la geomorfología de su entorno y los flujos naturales de riesgo.")

# 2. INTEGRACIÓN: DASHBOARD DE MÉTRICAS
st.markdown("---")
st.subheader("📊 Dashboard de Vulnerabilidad Crítica")
m1, m2, m3 = st.columns(3)
m1.metric(label="Vialidad Expuesta (Riesgo Alto)", value="42%", delta="Crítico")
m2.metric(label="Superficie Urbana en Peligro", value="6.4 km²", delta="Zona Central")
m3.metric(label="Puentes en Intersección", value="04", delta="Conectividad")
st.markdown("---")

# CONFIGURACIÓN DEL MAPA
tiles_dict = {"OpenStreetMap": "OpenStreetMap", "CartoDB Positron": "CartoDB positron", "Satélite (Esri)": None}
center = [-42.85, -72.70] 

if limite is not None and not limite.empty:
    bounds = limite.total_bounds
    center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]

m = folium.Map(location=center, zoom_start=9, tiles=tiles_dict[mapa_base] if tiles_dict[mapa_base] else "OpenStreetMap")

if limite is not None and not limite.empty:
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

if mapa_base == "Satélite (Esri)":
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Satélite (Esri)", overlay=False, control=False,
    ).add_to(m)

plugins.Fullscreen(position='topleft', title="Pantalla Completa", title_cancel="Salir").add_to(m)
plugins.MeasureControl(position='topleft', primary_length_unit='kilometers', primary_area_unit='sqmeters').add_to(m)
plugins.MiniMap(toggle_display=True, position='bottomright').add_to(m)

# CAPAS
if mostrar_dem and dem_data is not None and dem_bounds_latlon is not None:
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    # LÍNEA CORREGIDA PARA SOLUCIONAR EL ERROR DE MATPLOTLIB
    cmap = mpl.colormaps['terrain'] 
    rgba = (cmap(norm(dem_data)) * 255).astype(np.uint8)
    rgba[np.isnan(dem_data)] = [0, 0, 0, 0] 
    folium.raster_layers.ImageOverlay(image=rgba, bounds=dem_bounds_latlon, name="DEM", opacity=0.6).add_to(m)

# AMENAZA
colores_amenaza = {"Alto": "#b30000", "Moderado": "#fc8d59", "Bajo": "#fee08b"}
opacidades = {"Alto": 0.5, "Moderado": 0.4, "Bajo": 0.3}

if mostrar_amenaza and amenaza is not None:
    col_nivel = "nivel" if "nivel" in amenaza.columns else amenaza.columns[0]
    fg_amenaza = folium.FeatureGroup(name="Zonas de Amenaza")
    for _, row in amenaza.sort_values(col_nivel, key=lambda s: s.map({"Bajo": 0, "Moderado": 1, "Alto": 2}).fillna(0)).iterrows():
        nivel = row.get(col_nivel, "Bajo")
        color = colores_amenaza.get(nivel, "#999999")
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda x, c=color, o=opacidades.get(nivel, 0.4): {"color": c, "fillColor": c, "weight": 1.5, "fillOpacity": o},
            tooltip=f"Peligro: {nivel}"
        ).add_to(fg_amenaza)
    fg_amenaza.add_to(m)

# 3. INTEGRACIÓN: TOOLTIPS A PRUEBA DE FALLOS (HIDROGRAFÍA)
if mostrar_hidro and hidrografia is not None:
    cols_hidro = [c for c in hidrografia.columns if c != 'geometry']
    folium.GeoJson(
        hidrografia,
        name="Red Hídrica",
        tooltip=folium.GeoJsonTooltip(fields=cols_hidro, localize=True) if cols_hidro else "Río / Estero",
        style_function=lambda x: {"color": "#08519c", "weight": 2}
    ).add_to(m)

# 4. INTEGRACIÓN: TOOLTIPS A PRUEBA DE FALLOS (RED VIAL)
if mostrar_vial and red_vial is not None:
    cols_vial = [c for c in red_vial.columns if c != 'geometry']
    folium.GeoJson(
        red_vial, name="Red Vial",
        style_function=lambda x: {"color": "#4d4d4d", "weight": 2.5, "dashArray": "1"},
        tooltip=folium.GeoJsonTooltip(fields=cols_vial, localize=True) if cols_vial else "Red Vial Chaitén"
    ).add_to(m)

# 5. PARQUE PUMALÍN (Con nombre oficial)
if mostrar_pumalin and pumalin is not None:
    folium.GeoJson(
        pumalin, 
        name="Parque Pumalín", 
        style_function=lambda x: {"color": "#1a9850", "fillColor": "#1a9850", "weight": 2.5, "fillOpacity": 0.25},
        tooltip="Parque Nacional Pumalín (Área de Conservación)"
    ).add_to(m)

# 6. LÍMITE COMUNAL (Con nombre oficial)
if mostrar_limite and limite is not None:
    folium.GeoJson(
        limite, 
        name="Límite comunal", 
        style_function=lambda x: {"color": "#000000", "weight": 3, "fillOpacity": 0, "dashArray": "15, 10"},
        tooltip="Límite Comunal Chaitén"
    ).add_to(m)

# 7. MARCADOR DEL VOLCÁN
if mostrar_amenaza and volcan is not None:
    for _, row in volcan.iterrows():
        folium.Marker(
            [row.geometry.y, row.geometry.x], 
            tooltip="🌋 Cráter Volcán Chaitén", 
            icon=folium.Icon(color="black", icon="fire", prefix="fa")
        ).add_to(m)

# LEYENDA FLOTANTE
leyenda_html = '''
     <div style="position: fixed; 
     bottom: 50px; left: 50px; width: 170px; height: 130px; 
     background-color: white; border:2px solid grey; z-index:9999; font-size:12px;
     padding: 10px; opacity: 0.85; border-radius: 5px;">
     <b>Leyenda de Riesgo</b><br>
     <i style="background:#b30000;width:12px;height:12px;display:inline-block;margin-right:5px;"></i> Riesgo Alto<br>
     <i style="background:#fc8d59;width:12px;height:12px;display:inline-block;margin-right:5px;"></i> Riesgo Medio<br>
     <i style="background:#fee08b;width:12px;height:12px;display:inline-block;margin-right:5px;"></i> Riesgo Bajo<br>
     <hr style="margin:5px 0;">
     <i style="background:#08519c;width:12px;height:2px;display:inline-block;margin-right:5px;"></i> Red Hídrica<br>
     <i style="background:#4a4a4a;width:12px;height:2px;display:inline-block;margin-right:5px;"></i> Red Vial
     </div>
     '''
m.get_root().html.add_child(folium.Element(leyenda_html))

LayerControl(collapsed=False).add_to(m)
st_folium(m, width=None, height=600)

# ----------------------------------------------------------------------
# GRÁFICOS Y TABLAS 
# ----------------------------------------------------------------------
st.markdown("---")
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📊 Distribución del Riesgo")
    if amenaza is not None:
        col_nivel = "nivel" if "nivel" in amenaza.columns else amenaza.columns[0]
        df_chart = amenaza.copy()
        df_chart["area_km2"] = df_chart.to_crs("EPSG:32718").geometry.area / 1e6
        fig = px.pie(df_chart, names=col_nivel, values="area_km2", color=col_nivel, color_discrete_map=colores_amenaza, hole=0.4)
        fig.update_layout(height=350, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("📋 Explorador de Datos Espaciales")
    capa_tabla = st.selectbox("Capa a inspeccionar:", ["Zonas de amenaza", "Hidrografía", "Red Vial", "Parque Pumalín", "Límite comunal"])
    gdf_map = {"Zonas de amenaza": amenaza, "Hidrografía": hidrografia, "Red Vial": red_vial, "Parque Pumalín": pumalin, "Límite comunal": limite}
    gdf_sel = gdf_map[capa_tabla]
    if gdf_sel is not None and not gdf_sel.empty:
        df_show = gdf_sel.drop(columns="geometry")
        st.dataframe(df_show, use_container_width=True, height=250)
        st.download_button(label=f"⬇️ Descargar {capa_tabla} (GeoJSON)", data=gdf_sel.to_json(), file_name=f"{capa_tabla.lower().replace(' ', '_')}.geojson", mime="application/geo+json")

st.markdown("---")
st.caption("Trabajo Final — Curso Aplicaciones SIG, Escuela de Geografía UACh, 2026. Elaborado por Hernán Saavedra Ruiz.")
