import streamlit as st
import pandas as pd

# Importaciones de módulos propios
from utils.data_processing import load_and_process_data
from utils.model import build_rsf_model
from utils.style_loader import load_custom_css
from utils.bigquery_connector import bigquery_auth, read_bq_alarms_safe, autorefresh
from viz.components import render_sidebar, render_tab1, render_tab2, render_tab3

load_custom_css()

# Configurar pandas para evitar warnings de downcasting
pd.set_option('future.no_silent_downcasting', True)

st.set_page_config(page_title="Command Center CRAC", layout="wide", initial_sidebar_state="expanded")

def main():
    df_raw = None
    
    try:
        # Configurar autorefresco cada 10 minutos
        autorefresh(time=10)
        credentials = bigquery_auth()
        
        if credentials:
            with st.spinner("📡 Cargando datos desde BD..."):
                df_raw = read_bq_alarms_safe(credentials)
            if df_raw is not None and not df_raw.empty:
                pass
            else:
                st.error("No se pudieron cargar datos desde BD")
                st.stop()
        else:
            st.error("No se pudo autenticar con BD")
            st.stop()
            
    except Exception as e:
        st.error(f"Error conectando a BD: {str(e)}")
        st.stop()

    # -----------------------
    # Data processing
    # -----------------------
    df = load_and_process_data(df_raw)

    # -----------------------
    # SIDEBAR - Unified Controls (sin umbral de severidad)
    # -----------------------
    risk_threshold, device_filter = render_sidebar(df)

    # -----------------------
    # Build RSF Model (cached)
    # -----------------------
    # Usar umbral fijo de severidad (configuración en back)
    SEVERITY_THRESHOLD = 6  # Umbral fijo para alarmas críticas
    rsf_model, intervals, features = build_rsf_model(df, SEVERITY_THRESHOLD)

    # Mostrar debug rápido para entender censurado/evento
    #with st.expander("🔎 Debug: resumen de intervals (útil para entender por qué se entrenó o no)"):
    #    if intervals is None or len(intervals) == 0:
    #        st.write("No se generaron intervals. Revisa el dataset y las columnas de fecha / dispositivo.")
    #    else:
    #        st.write("Primeras filas de 'intervals':")
    #        st.dataframe(intervals.head(10))
    #        st.write("Conteo de 'event' (0=censurado,1=falla):")
    #       st.write(intervals['event'].value_counts(dropna=False))
    #       st.write("Total intervals:", len(intervals))
    #       st.write("Total eventos (1):", int(intervals['event'].astype(bool).sum()))

    # -----------------------
    # MAIN DASHBOARD WITH TABS
    # -----------------------
    st.title("🏢 Command Center - Gestión Predictiva CRAC")

    tab1, tab2, tab3 = st.tabs(["📊 Resumen", "📈 Proyección de Riesgo", "🎯 Recomendaciones de Mantenimiento"])

    # Preparar datos para las pestañas - FILTRAR DISPOSITIVOS CONSISTENTEMENTE
    available_devices = sorted(df['Dispositivo'].unique())
    if device_filter:
        available_devices = [d for d in available_devices if d in device_filter]

    #plot_devices = available_devices[:top_n]

    # Mostrar información del filtro en el sidebar
    #if device_filter:
    #    st.sidebar.success(f"🔍 Filtro activo: {len(available_devices)} de {len(df['Dispositivo'].unique())} equipos")
    #else:
    #    st.sidebar.info(f"📋 Mostrando todos los {len(available_devices)} equipos disponibles")

    # Renderizar cada pestaña PASANDO LOS DISPOSITIVOS FILTRADOS
    with tab1:
        render_tab1(rsf_model, intervals, features, df, available_devices, risk_threshold)

    with tab2:
        render_tab2(rsf_model, intervals, available_devices, risk_threshold)

    with tab3:
        # Pasar los dispositivos disponibles ya filtrados
        render_tab3(rsf_model, intervals, df, risk_threshold, available_devices)

    st.markdown("---")
    last_update = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(f"<div style='text-align: center; color: #666; font-size: 10px; padding: 5px;'>Última actualización: {last_update}</div>",
                unsafe_allow_html=True)

if __name__ == "__main__":
    main()