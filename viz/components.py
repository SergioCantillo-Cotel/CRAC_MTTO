import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from utils.alerts import get_device_failures, hours_to_days_hours
from utils.model import calculate_time_to_threshold_risk
from utils.time_monitor import round_down_10_minutes
from viz.charts import predict_failure_risk_curves

def custom_metric(label, value, hint="", delta=None, color="#ffffff", bg_color="#0D2A2B"):
    """
    Métrica personalizada sencilla con hint y fondo
    """
    delta_html = ""
    if delta:
        delta_color = "#00ff00" if str(delta).startswith("+") else "#ff0000"
        delta_html = f'<div style="font-size: 14px; color: {delta_color}; margin-top: 5px;">{delta}</div>'
    
    tooltip = f'title="{hint}"' if hint else ""
    
    html = f"""
    <div style="background-color: {bg_color};padding: 1rem;border-radius: 0.5rem;text-align: center;cursor: help;" {tooltip}>
        <div style="font-size: 14px;color: #ffffff;margin-bottom: 2px;font-weight: 400;">
            {label}
        </div>
        <div style="font-size: 24px;color: {color};font-weight: 500;line-height: 0.8;">
            {value}
        </div>
        {delta_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def render_sidebar(container,df):
    """Renderiza el panel de control lateral dentro de un contenedor con borde"""
    # Slider que muestra porcentajes pero trabaja internamente con decimales
    risk_threshold_decimal = container.slider(
        "⚠️ Umbral de riesgo (%)",
        min_value=1.0, 
        max_value=100.0,
        value=80.0, 
        step=0.1,
        format="%.1f%%",  # Esto muestra 80% en lugar de 0.8
        help="Probabilidad de falla a monitorear (80% = alto riesgo)"
    )/100

    device_filter = container.multiselect("🔍 Filtrar dispositivos",
                                          options=sorted(df['Dispositivo'].unique()),
                                          default=[],
                                          help="Vacío = todos los dispositivos")
    
    return risk_threshold_decimal, device_filter

def render_tab1(rsf_model, intervals, features, df, available_devices, risk_threshold):
    """Renderiza la pestaña de resumen"""
    priority_col, summary_col = st.columns([3,1])

    with priority_col:
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
                            'riesgo_actual': current_risk,  # Ya está en porcentaje
                            'total_alarmas': total_alarms,
                            'tiempo_transcurrido': current_time,
                            'tiempo_transcurrido_dias': current_time / 24.0
                        })

            if maintenance_data:
                maintenance_df = pd.DataFrame(maintenance_data)
                maintenance_df = maintenance_df.sort_values(
                    ['tiempo_hasta_umbral', 'riesgo_actual'],
                    ascending=[True, False]).head(5)

                maintenance_df = maintenance_df.iloc[::-1]
                cont_top5 = st.container(key='cont-top5')
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
                                     f"Riesgo actual: {row['riesgo_actual']:.1f}%<br>" +  # Ya está en porcentaje
                                     f"Tiempo transcurrido: {row['tiempo_transcurrido_dias']:.1f} días<br>" +
                                     f"Total alarmas: {row['total_alarmas']}<extra></extra>"
                    ))

                fig_bar.update_layout(
                    paper_bgcolor='#0D2A2B',
                    height=360,
                    
                    title={
                        'text': f"🔧 Top {len(available_devices)} Equipos con Prioridad de Mantenimiento",
                        'x': 0.5, 'font': {'color':"#ffffff"},
                        'xanchor': 'center',
                    },
                    xaxis_title="Días hasta umbral de riesgo",
                    yaxis_title="Equipos",
                    showlegend=False,
                    margin=dict(l=30, r=40, t=55, b=30),
                    xaxis=dict(showline=True, linecolor='white', showgrid=False, zeroline=False, title_font=dict(color='white',family='Manrope'),tickfont=dict(color='white',family='Manrope')),
                    yaxis=dict(title_font=dict(color='white',family='Manrope'), tickfont=dict(color='white',family='Manrope'))
                )

                cont_top5.plotly_chart(fig_bar, width='stretch', config={'displayModeBar': False})
            else:
                st.info("No hay equipos con riesgo futuro identificado")
        else:
            if rsf_model is None:
                st.warning("Modelo no disponible - datos insuficientes para entrenar el modelo predictivo (ver Debug).")
            else:
                st.info("El modelo predictivo proporcionará prioridades una vez entrenado")

    with summary_col:
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

            cont_alert = st.container(key='cont-alert')
            col1, col2 = cont_alert.columns(2)

            with col1:
                custom_metric("🔴 Crítico", critico, hint="Equipos que requieren atención inmediata (1-2 Horas)")
                custom_metric("🟠 Alto", alto, hint="Equipos que requieren mantenimiento próximamente")

            with col2:
                custom_metric("🟡 Medio", medio, hint="Equipos para planificación de mantenimiento a mediano plazo")
                custom_metric("🟢 Bajo", bajo, hint="Equipos con bajo riesgo inmediato")
                
            if critico + alto + medio + bajo > 0:
                fig_pie = go.Figure(data=[go.Pie(
                    labels=['Crítico', 'Alto', 'Medio', 'Bajo'],
                    values=[critico, alto, medio, bajo],
                    marker_colors=['#ef4444', '#f59e0b', '#eab308', '#22c55e'],
                    hole=.4,rotation=90
                )])

                fig_pie.update_layout(
                    paper_bgcolor='#0D2A2B',
                    height=200,
                    margin=dict(l=10, r=0, t=30, b=10),
                    showlegend=False,
                    title_x=0.5, title='',
                    font=dict(color='white',family='Manrope'),
                )
                cont_alert.plotly_chart(fig_pie, width='stretch', config={'displayModeBar': False})
        else:
            st.info(f"Sin datos de riesgo para los {available_devices_count} equipos seleccionados")
    else:
        st.info("Esperando datos del modelo")

def render_tab2(rsf_model, intervals, plot_devices, risk_threshold):
    """Renderiza la pestaña de proyección de riesgo"""
    top_n = st.slider("📊 Número de equipos a mostrar",key="slider_tab2",
                      min_value=0,
                      max_value=len(plot_devices),
                      value=min(5, len(plot_devices)))

    plot_devices = plot_devices[:top_n]

    if rsf_model is not None and len(plot_devices) > 0:
        with st.spinner("Calculando proyecciones de riesgo..."):
            fig = predict_failure_risk_curves(rsf_model, intervals, plot_devices,
                                            risk_threshold=risk_threshold,
                                            max_time=5000)

            fig.update_layout(
                paper_bgcolor='#113738',
                plot_bgcolor='#113738', 
                height=450,
                xaxis_title="Días desde ahora",
                yaxis_title="Probabilidad de Falla (%)",  # Agregar % al título
                margin=dict(l=10, r=10, t=30, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=-1.22),
                hovermode="closest",
                xaxis=dict(range=[0, 5000 / 24], showline=True, linecolor='white', showgrid=False, zeroline=False, title_font=dict(color='white',family='Manrope'),tickfont=dict(color='white',family='Manrope')),
                yaxis=dict(
                    title_font=dict(color='white',family='Manrope'), 
                    tickfont=dict(color='white',family='Manrope'),
                    ticksuffix="%",  # Agregar % a los ticks del eje Y
                    range=[0, 100]   # Rango de 0% a 100%
                )
            )
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': True})
    else:
        if rsf_model is None:
            st.warning("Modelo no disponible - datos insuficientes para entrenar el modelo predictivo (ver Debug).")
        else:
            st.info("No hay dispositivos para mostrar con los filtros actuales")

def render_tab3(rsf_model, intervals, df, risk_threshold, available_devices=None, 
                last_maintenance_dict=None, client_dict=None):
    """Renderiza la pestaña de recomendaciones de mantenimiento USANDO DISPOSITIVOS FILTRADOS"""
    # Si no se proporcionan dispositivos disponibles, usar todos
    if available_devices is None:
        available_devices = sorted(df['Dispositivo'].unique())
    
    # Inicializar diccionarios si no se proporcionan
    if last_maintenance_dict is None:
        last_maintenance_dict = {}
    if client_dict is None:
        client_dict = {}
    
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
                        'riesgo_actual': current_risk,  # Ya está en porcentaje
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

                _render_maintenance_sections(critico_df, alto_df, planificar_df, df, 
                                           last_maintenance_dict, client_dict)
            else:
                st.success("✅ No hay equipos que requieran mantenimiento inmediato")
        else:
            st.info("No hay equipos con riesgo identificado para los dispositivos seleccionados")
    else:
        st.info("El modelo predictivo proporcionará recomendaciones una vez entrenado")

def _render_maintenance_sections(critico_df, alto_df, planificar_df, df, 
                               last_maintenance_dict, client_dict):
    """Renderiza las secciones de mantenimiento con información de último mantenimiento y cliente"""
    
    def format_maintenance_date(date):
        """Formatea la fecha de mantenimiento de manera amigable"""
        if pd.isna(date) or date is None:
            return "Nunca"
        
        try:
            # Si es una fecha reciente (últimos 30 días), mostrar "hace X días"
            from datetime import datetime
            days_ago = (datetime.now().date() - date.date()).days
            
            if days_ago == 0:
                return "Hoy"
            elif days_ago == 1:
                return "Ayer"
            elif days_ago < 7:
                return f"Hace {days_ago} días"
            elif days_ago < 30:
                weeks = days_ago // 7
                return f"Hace {weeks} semana{'s' if weeks > 1 else ''}"
            else:
                return date.strftime("%d/%m/%Y")
                
        except:
            return date.strftime("%d/%m/%Y") if hasattr(date, 'strftime') else str(date)
    
    def render_device_card(row, device_failures, last_maintenance_dict, client_dict, color_scheme):
        """Renderiza una tarjeta individual de dispositivo"""
        # Obtener información de mantenimiento
        serial = row['serial']
        last_maintenance = last_maintenance_dict.get(serial)
        client = client_dict.get(serial, "No especificado")
        
        maintenance_text = format_maintenance_date(last_maintenance)
        
        # Configurar colores según la categoría
        colors = {
            'critico': {'bg': '#fef2f2', 'border': '#ef4444', 'text': '#dc2626'},
            'alto': {'bg': '#fffbeb', 'border': '#f59e0b', 'text': '#d97706'},
            'planificar': {'bg': '#f0f9ff', 'border': '#0ea5e9', 'text': '#0369a1'}
        }
        
        color_set = colors.get(color_scheme, colors['planificar'])
        
        st.markdown(f"""
        <div style='background-color: {color_set['bg']}; border-left: 5px solid {color_set['border']}; padding: 15px; margin: 10px 0; border-radius: 5px;'>
            <h4 style='margin: 0; color: {color_set['text']};'>{row['equipo']}</h4>
            <p style='margin: 5px 0; font-size: 14px; color:#000000;'>
            <strong>🔢 Serial: {row['serial']}</strong><br>
            <strong>🏢 Cliente: {client}</strong><br>
            <strong>🔧 Último mantenimiento: {maintenance_text}</strong><br>
            <strong>⏱️ {hours_to_days_hours(row['tiempo_hasta_umbral'])}</strong> hasta umbral<br>
            <strong>📊 {row['riesgo_actual']:.1f}%</strong> riesgo actual<br>  <!-- Ya está en porcentaje -->
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
    
    # Renderizar sección CRÍTICO
    if len(critico_df) > 0:
        with st.container(key="exp-rojo"):
            with st.expander(f"🚨 **MANTENIMIENTO INMEDIATO REQUERIDO** ({len(critico_df)} equipos)", expanded=True):
                n_criticos = len(critico_df)
                crit_cols = st.columns(min(3, n_criticos))

                for idx, (_, row) in enumerate(critico_df.iterrows()):
                    with crit_cols[idx % len(crit_cols)]:
                        device_failures = get_device_failures(df, row['equipo'])
                        render_device_card(row, device_failures, last_maintenance_dict, client_dict, 'critico')

    # Renderizar sección ALTO
    if len(alto_df) > 0:
        with st.container(key="exp-amarillo"):
            with st.expander(f"⚠️ **MANTENIMIENTO PRÓXIMO** ({len(alto_df)} equipos)", expanded=True):
                n_altos = len(alto_df)
                alto_cols = st.columns(min(3, n_altos))

                for idx, (_, row) in enumerate(alto_df.iterrows()):
                    with alto_cols[idx % len(alto_cols)]:
                        device_failures = get_device_failures(df, row['equipo'])
                        render_device_card(row, device_failures, last_maintenance_dict, client_dict, 'alto')

    # Renderizar sección PLANIFICAR
    if len(planificar_df) > 0:
        with st.container(key="exp-azul"):
            with st.expander(f"📅 **MANTENIMIENTO PLANIFICADO** ({len(planificar_df)} equipos)", expanded=True):
                n_planificar = len(planificar_df)
                plan_cols = st.columns(min(3, n_planificar))

                for idx, (_, row) in enumerate(planificar_df.iterrows()):
                    with plan_cols[idx % len(plan_cols)]:
                        device_failures = get_device_failures(df, row['equipo'])
                        render_device_card(row, device_failures, last_maintenance_dict, client_dict, 'planificar')

def render_user_info():
    """Renderiza información del usuario en el sidebar"""
    if st.session_state.get('authenticated', False):
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**👤 Usuario:** {st.session_state.get('username', 'N/A')}")
        st.sidebar.markdown(f"**🎯 Rol:** {st.session_state.get('user_role', 'N/A')}")


def render_footer():
    last_update = round_down_10_minutes()
    st.markdown(
        f"<div style='text-align: center; color: #fff; font-size: 12px; padding: 0px;'>"
        f"Última actualización: {last_update}"
        f"</div>", 
        unsafe_allow_html=True
    )