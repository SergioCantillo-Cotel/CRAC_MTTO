# app.py
import streamlit as st
import pandas as pd
from PIL import Image
from utils.bigquery_connector import EQUIPO_SERIAL_MAPPING

# Importaciones de módulos propios
from utils.data_processing import load_and_process_data
from utils.model import build_rsf_model
from utils.style_loader import load_custom_css
from utils.bigquery_connector import bigquery_auth, read_bq_alarms_safe, autorefresh, completar_seriales_faltantes
from viz.components import render_sidebar, render_tab1, render_tab2, render_tab3, render_footer
from viz.auth_config import init_session_state, render_sidebar_login, render_sidebar_user_info, require_auth
from utils.maintenance_data import load_maintenance_data, get_maintenance_metadata
import streamlit.components.v1 as components


load_custom_css()
pd.set_option('future.no_silent_downcasting', True)

st.set_page_config(
    page_title="Command Center CRAC", 
    layout="wide", initial_sidebar_state="expanded"
)

image = Image.open('img/cotel_small.png')
st.logo(image,size='large')
st.markdown("<h2 style='color: white; margin-top: 10px; margin-bottom: 0; line-height: 1.2; padding-bottom: 0;'>🏢 Command Center - Gestión Predictiva CRAC</h2>", 
            unsafe_allow_html=True)

def render_public_interface():
    """Interfaz pública cuando no hay usuario autenticado"""
    components.html("""
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
    .welcome-text {
        background: #113738;padding: 30px;
        border-radius: 15px;
        border-left: 6px solid #203a28;
        margin: 20px 0px;
        box-shadow: 0 8px 25px rgba(0, 0, 0, 0.2);
        font-family: 'Manrope', sans-serif;
        color: white;
    }

    .welcome-text h4 {
        color: white;
        margin-top:0px;
        margin-bottom: 20px;
        font-weight: 700;
        font-size: 1.6rem;
    }

    .welcome-text p {
        color: white;
        margin-bottom: 15px;
        font-size: 1.0rem;
    }

    .welcome-text ul {
        color: white;
        margin-left: 10px;
        line-height: 1.5;
        font-size: 1.0rem;
    }

    .welcome-text li {
        color: white;
        margin-bottom: 12px;
        padding-left: 10px;
    }

    .welcome-text strong {
        color: white;
    }
    </style>

    <div class="welcome-text">
        <h4>¡Bienvenido al Sistema de Monitoreo CRAC!</h4>
        <p>Esta plataforma te permite:</p>
        <ul>
            <li>📊 <strong>Monitorear</strong> el estado de los equipos CRAC</li>
            <li>📈 <strong>Predecir</strong> fallas antes de que ocurran</li>
            <li>🎯 <strong>Optimizar</strong> el mantenimiento preventivo</li>
        </ul>
    </div>
    """, height=500)

def render_authenticated_interface():
    """Interfaz para usuarios autenticados"""
    df_raw = None
    
    try:
        # Configurar autorefresco cada 10 minutos
        autorefresh(time=10)
        credentials = bigquery_auth()
        
        if credentials:
            # -----------------------
            # MAIN DASHBOARD WITH TABS
            # -----------------------
            tab1, tab2, tab3 = st.tabs(["📊 Resumen", "📈 Proyección de Riesgo", "🎯 Recomendaciones de Mantenimiento"])
            with st.spinner("📡 Conectando con la base de datos..."):
                # PRIMERO: Obtener TODOS los datos sin filtrar
                df_raw_complete = read_bq_alarms_safe(credentials)
                
                # LUEGO: Filtrar por usuario para visualización
                cliente = st.session_state.user_info['name']
                if cliente and cliente != "Admin":  # Solo filtrar si no es admin
                    df_raw_user = df_raw_complete[df_raw_complete["Dispositivo"].str.contains(cliente, case=False, na=False)]
                else:
                    df_raw_user = df_raw_complete.copy()
                
            if df_raw_complete is not None and not df_raw_complete.empty:
                pass
            else:
                st.error("No se pudieron cargar datos desde la base de datos")
                st.stop()
        else:
            st.error("No se pudo establecer conexión con la base de datos")
            st.stop()
            
    except Exception as e:
        st.error(f"Error en la conexión: {str(e)}")
        st.stop()

    # -----------------------
    # Data processing - PROCESAR DATOS COMPLETOS PARA MODELO
    # -----------------------
    with st.spinner("🔄 Procesando información de equipos..."):
        # Procesar datos COMPLETOS para el modelo
        df_raw_complete_processed = completar_seriales_faltantes(df_raw_complete)
        df_complete = load_and_process_data(df_raw_complete_processed)
        
        # Procesar datos del USUARIO para visualización
        df_raw_user_processed = completar_seriales_faltantes(df_raw_user)
        df_user = load_and_process_data(df_raw_user_processed)

    # -----------------------
    # Cargar datos de mantenimiento - VERSIÓN OPTIMIZADA
    # -----------------------
    with st.spinner("📋 Cargando historial de mantenimientos..."):
        seriales = df_raw_user_processed['Serial_dispositivo'].unique()
        df_mttos = load_maintenance_data(seriales)
        # Usar la nueva función unificada para obtener todos los metadatos
        last_maintenance_dict, client_dict, brand_dict, model_dict = get_maintenance_metadata(df_mttos)

    container = st.sidebar.expander(f"Panel de Control",expanded=True,icon="🎛️")
    risk_threshold, device_filter = render_sidebar(container, df_user)

    SEVERITY_THRESHOLD = 6
    
    with st.spinner("🤖 Analizando patrones de comportamiento..."):
        # PASA last_maintenance_dict AL CONSTRUIR EL MODELO
        rsf_model, intervals, features = build_rsf_model(df_complete, SEVERITY_THRESHOLD, last_maintenance_dict)

    # -----------------------
    # APLICAR FILTROS DEL SIDEBAR SOBRE LOS DATOS DEL USUARIO
    # -----------------------
    available_devices = sorted(df_user['Dispositivo'].unique())
    if device_filter:
        available_devices = device_filter.copy()

    # Renderizar cada pestaña usando el MISMO MODELO (entrenado con todos los datos)
    # pero mostrando solo los datos del usuario
    with tab1:
        render_tab1(rsf_model, intervals, features, df_user, available_devices, risk_threshold, 
                   brand_dict, model_dict)
        render_footer()

    with tab2:
        render_tab2(rsf_model, intervals, available_devices, risk_threshold, 
                   brand_dict, model_dict, df_user)
        render_footer()

    with tab3:
        render_tab3(rsf_model, intervals, df_user, risk_threshold, available_devices, 
                   last_maintenance_dict, client_dict, brand_dict, model_dict)
        render_footer()

def main():
    """Función principal que maneja la autenticación"""
    # Inicializar estado de la sesión
    init_session_state()
    
    # Renderizar login en el sidebar (siempre)
    if not require_auth():
        render_sidebar_login()
    else:
        render_sidebar_user_info()
    
    # Renderizar contenido principal según autenticación
    if require_auth():
        render_authenticated_interface()
    else:
        render_public_interface()

if __name__ == "__main__":
    main()