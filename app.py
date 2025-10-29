# app.py
import streamlit as st
import pandas as pd
from PIL import Image

# Importaciones de módulos propios
from utils.data_processing import load_and_process_data
from utils.model import build_rsf_model
from utils.style_loader import load_custom_css
from utils.bigquery_connector import bigquery_auth, read_bq_alarms_safe, autorefresh, completar_seriales_faltantes
from viz.components import render_sidebar, render_tab1, render_tab2, render_tab3
from viz.auth_config import init_session_state, render_sidebar_login, render_sidebar_user_info, require_auth
from utils.maintenance_data import load_maintenance_data, get_last_maintenance_by_serial, get_client_by_serial

load_custom_css()

# Configurar pandas para evitar warnings de downcasting
pd.set_option('future.no_silent_downcasting', True)

st.set_page_config(
    page_title="Command Center CRAC", 
    layout="wide", initial_sidebar_state="expanded"
)

image = Image.open('img/cotel_small.png')
st.logo(image,size='large')

def render_public_interface():
    """Interfaz pública cuando no hay usuario autenticado"""
    st.title("🏢 Command Center - Gestión Predictiva CRAC")
    st.markdown("""
        ### Bienvenido al Sistema de Monitoreo CRAC
        
        Esta plataforma te permite:
        - 📊 **Monitorear** el estado de los equipos CRAC
        - 📈 **Predecir** fallas antes de que ocurran  
        - 🎯 **Optimizar** el mantenimiento preventivo
    """)
    
    # Mostrar información de demo (opcional)
    #with st.expander("ℹ️ Información de acceso (Demo)"):
    #    st.write("**Credenciales de prueba:**")
    #    st.write("- **Usuario:** admin | **Contraseña:** admin123")
    #    st.write("- **Usuario:** operador | **Contraseña:** operador123")

def render_authenticated_interface():
    """Interfaz para usuarios autenticados"""
    df_raw = None
    
    try:
        # Configurar autorefresco cada 10 minutos
        autorefresh(time=10)
        credentials = bigquery_auth()
        
        if credentials:
            with st.spinner("📡 Conectando con la base de datos..."):
                df_raw = read_bq_alarms_safe(credentials)
            if df_raw is not None and not df_raw.empty:
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
    # Cargar datos de mantenimiento
    # -----------------------
    with st.spinner("📋 Cargando historial de mantenimientos..."):
        df_mttos = load_maintenance_data()
        last_maintenance_dict = get_last_maintenance_by_serial(df_mttos)
        client_dict = get_client_by_serial(df_mttos)

    # -----------------------
    # Data processing
    # -----------------------
    with st.spinner("🔄 Procesando información de equipos..."):
        df_raw = completar_seriales_faltantes(df_raw)
        df = load_and_process_data(df_raw)

    # -----------------------
    # SIDEBAR - Unified Controls
    # -----------------------
    risk_threshold, device_filter = render_sidebar(df)

    # -----------------------
    # Build RSF Model (cached)
    # -----------------------
    # Usar umbral fijo de severidad (configuración en back)
    SEVERITY_THRESHOLD = 6  # Umbral fijo para alarmas críticas
    
    with st.spinner("🤖 Analizando patrones de comportamiento..."):
        rsf_model, intervals, features = build_rsf_model(df, SEVERITY_THRESHOLD)

    # -----------------------
    # MAIN DASHBOARD WITH TABS
    # -----------------------
    st.title("🏢 Command Center - Gestión Predictiva CRAC")

    tab1, tab2, tab3 = st.tabs(["📊 Resumen", "📈 Proyección de Riesgo", "🎯 Recomendaciones de Mantenimiento"])

    # Preparar datos para las pestañas - FILTRAR DISPOSITIVOS CONSISTENTEMENTE
    available_devices = sorted(df['Dispositivo'].unique())
    if device_filter:
        available_devices = [d for d in available_devices if d in device_filter]

    # Renderizar cada pestaña PASANDO LOS DATOS DE MANTENIMIENTO
    with tab1:
        render_tab1(rsf_model, intervals, features, df, available_devices, risk_threshold)

    with tab2:
        render_tab2(rsf_model, intervals, available_devices, risk_threshold)

    with tab3:
        # Pasar los dispositivos disponibles y los datos de mantenimiento
        render_tab3(
            rsf_model, intervals, df, risk_threshold, 
            available_devices, last_maintenance_dict, client_dict
        )

    st.markdown("---")
    last_update = (pd.Timestamp.now() - pd.Timedelta(hours=5).strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(f"<div style='text-align: center; color: #666; font-size: 10px; padding: 5px;'>Última actualización: {last_update}</div>",
                unsafe_allow_html=True)

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
