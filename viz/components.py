import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from utils.alerts import get_device_failures, hours_to_days_hours
from utils.model import calculate_time_to_threshold_risk
from .charts import predict_failure_risk_curves

def render_sidebar(df):
    """Renderiza el panel de control lateral (sin umbral de severidad)"""
    st.sidebar.header("🎛️ Panel de Control")

    risk_threshold = st.sidebar.slider("🎯 Umbral de probabilidad de falla",
                                      min_value=0.1, max_value=0.95,
                                      value=0.8, step=0.01,
                                      help="Probabilidad de falla a monitorear (80% = alto riesgo)")

    device_filter = st.sidebar.multiselect("🔍 Filtrar dispositivos",
                                          options=sorted(df['Dispositivo'].unique()),
                                          default=[],
                                          help="Vacío = todos los dispositivos")
    
    return risk_threshold, device_filter

def render_tab1(rsf_model, intervals, features, df, available_devices, risk_threshold):
    """Renderiza la pestaña de resumen"""
    priority_col, summary_col = st.columns([2, 1])

    with priority_col:
        st.subheader("🔧 Equipos con Prioridad de Mantenimiento")

        if rsf_model is not None and len(intervals) > 0:
            maintenance_data = []
            
            for device in available_devices:
                time_to_threshold, threshold_risk, current_time = calculate_time_to_threshold_risk(
                    rsf_model, intervals, device, risk_threshold, 5000)

                if time_to_threshold is not None and time_to_threshold > 0:
                    device_intervals = intervals[intervals['unit'] == device]
                    if len(device_intervals) > 0:
                        latest_interval = device_intervals.iloc[-1]
                        total_alarms = latest_interval['total_alarms']

                        feature_values = latest_interval[features].fillna(0).infer_objects(copy=False).values
                        X_pred = pd.DataFrame([feature_values], columns=features)
                        surv_func = rsf_model.predict_survival_function(X_pred)[0]
                        current_risk = (1 - np.interp(current_time, surv_func.x, surv_func.y, left=1.0, right=surv_func.y[-1])) * 100

                        # Obtener el serial del dispositivo
                        device_data = df[df['Dispositivo'] == device]
                        serial = device_data['Serial_dispositivo'].iloc[0] if 'Serial_dispositivo' in device_data.columns and len(device_data) > 0 else "N/A"

                        maintenance_data.append({
                            'equipo': device,
                            'serial': serial,
                            'tiempo_hasta_umbral': time_to_threshold,
                            'tiempo_hasta_umbral_dias': time_to_threshold / 24.0,
                            'riesgo_actual': current_risk,
                            'total_alarmas': total_alarms,
                            'tiempo_transcurrido': current_time,
                            'tiempo_transcurrido_dias': current_time / 24.0
                        })

            if maintenance_data:
                maintenance_df = pd.DataFrame(maintenance_data)
                maintenance_df = maintenance_df.sort_values(
                    ['tiempo_hasta_umbral', 'riesgo_actual'],
                    ascending=[True, False]
                ).head(5)

                maintenance_df = maintenance_df.iloc[::-1]

                fig_bar = go.Figure()

                for i, (_, row) in enumerate(maintenance_df.iterrows()):
                    if row['tiempo_hasta_umbral_dias'] < 7:
                        color = '#ef4444'
                    elif row['tiempo_hasta_umbral_dias'] < 30:
                        color = '#f59e0b'
                    else:
                        color = '#22c55e'

                    fig_bar.add_trace(go.Bar(
                        y=[row['equipo']],
                        x=[row['tiempo_hasta_umbral_dias']],
                        orientation='h',
                        name=row['equipo'],
                        marker_color=color,
                        hovertemplate=f"<b>{row['equipo']}</b><br>" +
                                     f"Serial: {row['serial']}<br>" +
                                     f"Tiempo hasta {int(risk_threshold*100)}% riesgo: {row['tiempo_hasta_umbral_dias']:.1f} días<br>" +
                                     f"Riesgo actual: {row['riesgo_actual']:.1f}%<br>" +
                                     f"Tiempo transcurrido: {row['tiempo_transcurrido_dias']:.1f} días<br>" +
                                     f"Total alarmas: {row['total_alarmas']}<extra></extra>"
                    ))

                fig_bar.update_layout(
                    template="plotly_white",
                    height=400,
                    xaxis_title="Días hasta alcanzar umbral de riesgo",
                    yaxis_title="Equipos",
                    showlegend=False,
                    margin=dict(l=0, r=0, t=20, b=0),
                    xaxis=dict(showline=True, linecolor='black', showgrid=False, zeroline=False, title_font=dict(color='black',family='Poppins'),tickfont=dict(color='black',family='Poppins')),
                    yaxis=dict(title_font=dict(color='black',family='Poppins'), tickfont=dict(color='black',family='Poppins'))
                )

                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("No hay equipos con riesgo futuro identificado")
        else:
            if rsf_model is None:
                st.warning("Modelo no disponible - datos insuficientes para entrenar el modelo predictivo (ver Debug).")
            else:
                st.info("El modelo predictivo proporcionará prioridades una vez entrenado")

    with summary_col:
        # Pasar el conteo de dispositivos disponibles (filtrados) para el contexto
        available_devices_count = len(available_devices)
        _render_summary_col(rsf_model, intervals, 
                          maintenance_data if 'maintenance_data' in locals() else None,
                          available_devices_count)

def _render_summary_col(rsf_model, intervals, maintenance_data, available_devices_count):
    """Renderiza la columna de resumen CON FILTRO DE EQUIPOS"""
    if rsf_model is not None and len(intervals) > 0:
        if maintenance_data and len(maintenance_data) > 0:
            all_maintenance_df = pd.DataFrame(maintenance_data)

            # Calcular métricas SOLO para los dispositivos con datos de mantenimiento
            critico = len(all_maintenance_df[all_maintenance_df['tiempo_hasta_umbral_dias'] < 7])
            alto = len(all_maintenance_df[(all_maintenance_df['tiempo_hasta_umbral_dias'] >= 7) &
                                        (all_maintenance_df['tiempo_hasta_umbral_dias'] < 30)])
            medio = len(all_maintenance_df[(all_maintenance_df['tiempo_hasta_umbral_dias'] >= 30) &
                                         (all_maintenance_df['tiempo_hasta_umbral_dias'] < 90)])
            bajo = len(all_maintenance_df[all_maintenance_df['tiempo_hasta_umbral_dias'] >= 90])

            col1, col2 = st.columns(2)

            with col1:
                st.metric("🔴 Crítico", critico, help="Equipos que requieren atención inmediata (1-2 Horas)")
                st.metric("🟠 Alto", alto, help="Equipos que requieren atención próxima")

            with col2:
                st.metric("🟡 Medio", medio, help="Equipos para planificación a mediano plazo")
                st.metric("🟢 Bajo", bajo, help="Equipos con bajo riesgo inmediato")

            if critico + alto + medio + bajo > 0:
                fig_pie = go.Figure(data=[go.Pie(
                    labels=['Crítico', 'Alto', 'Medio', 'Bajo'],
                    values=[critico, alto, medio, bajo],
                    marker_colors=['#ef4444', '#f59e0b', '#eab308', '#22c55e'],
                    hole=.4
                )])

                fig_pie.update_layout(
                    template="plotly_white",
                    height=250,
                    margin=dict(l=0, r=0, t=0, b=0),
                    showlegend=False,
                    title_x=0.5, title='',
                    font=dict(color='black',family='Poppins'),
                )
                st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info(f"Sin datos de riesgo para los {available_devices_count} equipos seleccionados")
    else:
        st.info("Esperando datos del modelo")

def render_tab2(rsf_model, intervals, plot_devices, risk_threshold):

    top_n = st.slider("📊 Número de equipos a mostrar",
                      min_value=0,
                      max_value=len(plot_devices),
                      value=min(5, len(plot_devices)))

    plot_devices = plot_devices[:top_n]

    """Renderiza la pestaña de proyección de riesgo"""
    if rsf_model is not None and len(plot_devices) > 0:
        with st.spinner("Calculando proyecciones de riesgo..."):
            fig = predict_failure_risk_curves(rsf_model, intervals, plot_devices,
                                            risk_threshold=risk_threshold,
                                            max_time=5000)

            fig.update_layout(
                template="plotly_white",
                height=450,
                xaxis_title="Días desde ahora",
                yaxis_title="Probabilidad de Falla",
                margin=dict(l=0, r=0, t=30, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=-1.22),
                hovermode="closest",
                xaxis=dict(range=[0, 5000 / 24])
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})

        st.info("💡 **Leyenda:** ◊ Tiempo actual | ✕ Tiempo hasta alcanzar umbral de riesgo | Línea roja: Umbral de alerta")
    else:
        if rsf_model is None:
            st.warning("Modelo no disponible - datos insuficientes para entrenar el modelo predictivo (ver Debug).")
        else:
            st.info("No hay dispositivos para mostrar con los filtros actuales")

def render_tab3(rsf_model, intervals, df, risk_threshold, available_devices=None):
    """Renderiza la pestaña de recomendaciones de mantenimiento USANDO DISPOSITIVOS FILTRADOS"""
    # Si no se proporcionan dispositivos disponibles, usar todos
    if available_devices is None:
        available_devices = sorted(df['Dispositivo'].unique())
    
    if rsf_model is not None and len(intervals) > 0:
        # Recalcular maintenance_data SOLO para los dispositivos disponibles (filtrados)
        maintenance_data = []
        
        for device in available_devices:
            time_to_threshold, threshold_risk, current_time = calculate_time_to_threshold_risk(
                rsf_model, intervals, device, risk_threshold, 5000)

            if time_to_threshold is not None and time_to_threshold > 0:
                device_intervals = intervals[intervals['unit'] == device]
                if len(device_intervals) > 0:
                    latest_interval = device_intervals.iloc[-1]
                    total_alarms = latest_interval['total_alarms']

                    feature_values = latest_interval[['total_alarms', 'alarms_last_24h', 'time_since_last_alarm_h']].fillna(0).infer_objects(copy=False).values
                    X_pred = pd.DataFrame([feature_values], columns=['total_alarms', 'alarms_last_24h', 'time_since_last_alarm_h'])
                    surv_func = rsf_model.predict_survival_function(X_pred)[0]
                    current_risk = (1 - np.interp(current_time, surv_func.x, surv_func.y, left=1.0, right=surv_func.y[-1])) * 100

                    # Obtener el serial del dispositivo
                    device_data = df[df['Dispositivo'] == device]
                    serial = device_data['Serial_dispositivo'].iloc[0] if 'Serial_dispositivo' in device_data.columns and len(device_data) > 0 else "N/A"

                    maintenance_data.append({
                        'equipo': device,
                        'serial': serial,
                        'tiempo_hasta_umbral': time_to_threshold,
                        'tiempo_hasta_umbral_dias': time_to_threshold / 24.0,
                        'riesgo_actual': current_risk,
                        'total_alarmas': total_alarms,
                        'tiempo_transcurrido': current_time,
                        'tiempo_transcurrido_dias': current_time / 24.0
                    })

        if maintenance_data and len(maintenance_data) > 0:
            maintenance_df_all = pd.DataFrame(maintenance_data)
            maintenance_df_positive = maintenance_df_all[maintenance_df_all['tiempo_hasta_umbral'] > 0]

            if len(maintenance_df_positive) > 0:
                critico_df = maintenance_df_positive[maintenance_df_positive['tiempo_hasta_umbral_dias'] < 7]
                critico_df = critico_df.sort_values(['tiempo_hasta_umbral', 'riesgo_actual'], ascending=[True, False])

                alto_df = maintenance_df_positive[(maintenance_df_positive['tiempo_hasta_umbral_dias'] >= 7) &
                                                (maintenance_df_positive['tiempo_hasta_umbral_dias'] < 30)]
                alto_df = alto_df.sort_values(['tiempo_hasta_umbral', 'riesgo_actual'], ascending=[True, False])

                planificar_df = maintenance_df_positive[maintenance_df_positive['tiempo_hasta_umbral_dias'] >= 30]
                planificar_df = planificar_df.sort_values(['tiempo_hasta_umbral', 'riesgo_actual'], ascending=[True, False])

                _render_maintenance_sections(critico_df, alto_df, planificar_df, df)
            else:
                st.success("✅ No hay equipos que requieran mantenimiento inmediato")
        else:
            st.info("No hay equipos con riesgo identificado para los dispositivos seleccionados")
    else:
        st.info("El modelo predictivo proporcionará recomendaciones una vez entrenado")

def _render_maintenance_sections(critico_df, alto_df, planificar_df, df):
    """Renderiza las secciones de mantenimiento - SIEMPRE mostrar desplegable de fallas"""
    if len(critico_df) > 0:
        with st.expander(f"🚨 **MANTENIMIENTO INMEDIATO REQUERIDO** ({len(critico_df)} equipos)", expanded=True):
            n_criticos = len(critico_df)
            crit_cols = st.columns(min(3, n_criticos))

            for idx, (_, row) in enumerate(critico_df.iterrows()):
                with crit_cols[idx % len(crit_cols)]:
                    device_failures = get_device_failures(df, row['equipo'])

                    with st.container():
                        st.markdown(f"""
                        <div style='background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 15px; margin: 10px 0; border-radius: 5px;'>
                            <h4 style='margin: 0; color: #dc2626;'>{row['equipo']}</h4>
                            <p style='margin: 5px 0; font-size: 14px;'>
                            <strong>🔢 Serial: {row['serial']}</strong><br>
                            <strong>⏱️ {hours_to_days_hours(row['tiempo_hasta_umbral'])}</strong> hasta umbral<br>
                            <strong>📊 {row['riesgo_actual']:.1f}%</strong> riesgo actual<br>
                            <strong>🕐 {hours_to_days_hours(row['tiempo_transcurrido'])}</strong> transcurrido
                            </p>
                        </div>
                        """, unsafe_allow_html=True)

                    # SIEMPRE mostrar el desplegable de fallas (aunque esté vacío)
                    with st.expander("🔍 Fallas detectadas", expanded=False):
                        if device_failures:
                            for failure in device_failures:
                                st.write(f"• {failure}")
                        else:
                            st.info("No se detectaron fallas comunes específicas")

    if len(alto_df) > 0:
        with st.expander(f"⚠️ **MANTENIMIENTO PRÓXIMO** ({len(alto_df)} equipos)", expanded=True):
            n_altos = len(alto_df)
            alto_cols = st.columns(min(3, n_altos))

            for idx, (_, row) in enumerate(alto_df.iterrows()):
                with alto_cols[idx % len(alto_cols)]:
                    device_failures = get_device_failures(df, row['equipo'])

                    with st.container():
                        st.markdown(f"""
                        <div style='background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 15px; margin: 10px 0; border-radius: 5px;'>
                            <h4 style='margin: 0; color: #d97706;'>{row['equipo']}</h4>
                            <p style='margin: 5px 0; font-size: 14px;'>
                            <strong>🔢 Serial: {row['serial']}</strong><br>
                            <strong>⏱️ {hours_to_days_hours(row['tiempo_hasta_umbral'])}</strong> hasta umbral<br>
                            <strong>📊 {row['riesgo_actual']:.1f}%</strong> riesgo actual<br>
                            <strong>🕐 {hours_to_days_hours(row['tiempo_transcurrido'])}</strong> transcurrido
                            </p>
                        </div>
                        """, unsafe_allow_html=True)

                    # SIEMPRE mostrar el desplegable de fallas (aunque esté vacío)
                    with st.expander("🔍 Fallas detectadas", expanded=False):
                        if device_failures:
                            for failure in device_failures:
                                st.write(f"• {failure}")
                        else:
                            st.info("No se detectaron fallas comunes específicas")

    if len(planificar_df) > 0:
        with st.expander(f"📅 **MANTENIMIENTO PLANIFICADO** ({len(planificar_df)} equipos)", expanded=True):
            n_planificar = len(planificar_df)
            plan_cols = st.columns(min(3, n_planificar))

            for idx, (_, row) in enumerate(planificar_df.iterrows()):
                with plan_cols[idx % len(plan_cols)]:
                    device_failures = get_device_failures(df, row['equipo'])

                    with st.container():
                        st.markdown(f"""
                        <div style='background-color: #f0f9ff; border-left: 4px solid #0ea5e9; padding: 15px; margin: 10px 0; border-radius: 5px;'>
                            <h4 style='margin: 0; color: #0369a1;'>{row['equipo']}</h4>
                            <p style='margin: 5px 0; font-size: 14px;'>
                            <strong>🔢 Serial: {row['serial']}</strong><br>
                            <strong>⏱️ {hours_to_days_hours(row['tiempo_hasta_umbral'])}</strong> hasta umbral<br>
                            <strong>📊 {row['riesgo_actual']:.1f}%</strong> riesgo actual<br>
                            <strong>🕐 {hours_to_days_hours(row['tiempo_transcurrido'])}</strong> transcurrido
                            </p>
                        </div>
                        """, unsafe_allow_html=True)

                    # SIEMPRE mostrar el desplegable de fallas (aunque esté vacío)
                    with st.expander("🔍 Fallas detectadas", expanded=False):
                        if device_failures:
                            for failure in device_failures:
                                st.write(f"• {failure}")
                        else:
                            st.info("No se detectaron fallas comunes específicas")