import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
from utils.alerts import get_device_failures, hours_to_days_hours
from utils.model import calculate_time_to_threshold_risk
from utils.time_monitor import round_down_10_minutes
from viz.charts import predict_failure_risk_curves
from utils.maintenance_data import format_maintenance_date

def clean_device_name(device_name):
    """
    Elimina la parte del IP entre paréntesis del nombre del dispositivo
    Ejemplo: "FANALCA-Aire APC 1 (172.19.1.46)" -> "FANALCA-Aire APC 1"
    """
    if pd.isna(device_name) or not isinstance(device_name, str):
        return device_name
    
    # Eliminar contenido entre paréntesis (incluyendo los paréntesis)
    cleaned_name = re.sub(r'\s*\([^)]*\)$', '', device_name).strip()
    return cleaned_name

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
    risk_threshold_decimal = container.slider(
        "⚠️ Umbral de riesgo (%)",
        min_value=1.0, 
        max_value=100.0,
        value=80.0, 
        step=0.1,
        format="%.1f%%",
        help="Probabilidad de falla a monitorear (80% = alto riesgo)"
    )/100

    # Limpiar nombres de dispositivos para mostrar en el multiselect
    clean_device_names = [clean_device_name(device) for device in sorted(df['Dispositivo'].unique())]
    device_mapping = {clean_device_name(device): device for device in df['Dispositivo'].unique()}
    
    device_filter_clean = container.multiselect("🔍 Filtrar Equipos",
                                          options=clean_device_names,
                                          default=[],
                                          help="Vacío = todos los Equipos")
    
    # Mapear de vuelta a los nombres originales para el filtro
    device_filter = [device_mapping[clean_name] for clean_name in device_filter_clean]
    
    return risk_threshold_decimal, device_filter

def _get_device_display_info(device, df, brand_dict=None, model_dict=None):
    """Obtiene información unificada de dispositivo para display"""
    device_data = df[df['Dispositivo'] == device]
    if device_data.empty:
        return "N/A", "N/A", "N/A"
    
    serial = device_data['Serial_dispositivo'].iloc[0] if 'Serial_dispositivo' in device_data.columns and len(device_data) > 0 else "N/A"
    
    # Priorizar modelo del CRM, si no existe usar el de BigQuery
    model_crm = model_dict.get(serial, "N/A") if model_dict else "N/A"
    model_bigquery = device_data['Modelo'].iloc[0] if 'Modelo' in device_data.columns and len(device_data) > 0 else "N/A"
    model_display = model_crm if model_crm != "N/A" else model_bigquery
    
    brand = brand_dict.get(serial, "N/A") if brand_dict else "N/A"
    
    return serial, brand, model_display

def calcular_riesgo_actual(rsf_model, intervals, device, features):
    """
    Calcula el riesgo actual de un dispositivo
    
    Args:
        rsf_model: Modelo de supervivencia
        intervals: DataFrame con intervalos
        device: Nombre del dispositivo
        features: Lista de características del modelo
        
    Returns:
        float: Riesgo actual (0-100) o None si no se puede calcular
    """
    if rsf_model is None or intervals.empty:
        return None
    
    device_intervals = intervals[intervals['unit'] == device]
    if len(device_intervals) == 0:
        return None
    
    latest_interval = device_intervals.iloc[-1]
    current_time = latest_interval.get('current_time_elapsed', 0)
    
    # Obtener características
    feature_values = latest_interval[features].fillna(0).infer_objects(copy=False).values
    X_pred = pd.DataFrame([feature_values], columns=features)
    
    try:
        surv_func = rsf_model.predict_survival_function(X_pred)[0]
        current_risk = (1 - np.interp(current_time, surv_func.x, surv_func.y, 
                                      left=1.0, right=surv_func.y[-1])) * 100
        return float(current_risk)
    except:
        return None

def ordenar_dispositivos_por_riesgo(rsf_model, intervals, devices, features):
    """
    Ordena una lista de dispositivos por su riesgo actual (descendente)
    
    Args:
        rsf_model: Modelo de supervivencia
        intervals: DataFrame con intervalos
        devices: Lista de nombres de dispositivos
        features: Lista de características del modelo
        
    Returns:
        list: Dispositivos ordenados por riesgo actual (mayor a menor)
    """
    if rsf_model is None or not devices:
        return devices
    
    # Calcular riesgo para cada dispositivo
    device_risks = []
    for device in devices:
        risk = calcular_riesgo_actual(rsf_model, intervals, device, features)
        device_risks.append({
            'device': device,
            'risk': risk if risk is not None else -1  # -1 para dispositivos sin riesgo calculable
        })
    
    # Ordenar por riesgo descendente
    device_risks_sorted = sorted(device_risks, key=lambda x: x['risk'], reverse=True)
    
    # Retornar solo los nombres de dispositivos
    return [item['device'] for item in device_risks_sorted if item['risk'] >= 0]

def render_tab1(rsf_model, intervals, features, df, available_devices, risk_threshold, 
                brand_dict=None, model_dict=None):
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

                        serial, brand, model_display = _get_device_display_info(device, df, brand_dict, model_dict)

                        maintenance_data.append({
                            'equipo': device,
                            'equipo_clean': clean_device_name(device),
                            'serial': serial,
                            'marca': brand,
                            'modelo': model_display,
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

                    # Crear etiqueta mejorada con marca y modelo usando nombre limpio
                    device_label = f"{row['equipo_clean']}"
                    if row['marca'] != "N/A" and row['modelo'] != "N/A":
                        device_label = f"{row['equipo_clean']}"
                    elif row['marca'] != "N/A":
                        device_label = f"{row['equipo_clean']} ({row['marca']})"
                    elif row['modelo'] != "N/A":
                        device_label = f"{row['equipo_clean']} ({row['modelo']})"

                    fig_bar.add_trace(go.Bar(
                        y=[device_label],
                        x=[row['tiempo_hasta_umbral_dias']],
                        orientation='h',
                        name=row['equipo_clean'],
                        marker_color=color,
                        hovertemplate=f"<b>{row['equipo_clean']}</b><br>" +
                                     f"Serial: {row['serial']}<br>" +
                                     f"Marca: {row['marca']}<br>" +
                                     f"Modelo: {row['modelo']}<br>" +
                                     f"Tiempo hasta {int(risk_threshold*100)}% riesgo: {row['tiempo_hasta_umbral_dias']:.1f} días<br>" +
                                     f"Riesgo actual: {row['riesgo_actual']:.1f}%<br>" +
                                     f"Tiempo transcurrido: {row['tiempo_transcurrido_dias']:.1f} días<br>" +
                                     f"Total alarmas: {row['total_alarmas']}<extra></extra>"
                    ))

                fig_bar.update_layout(
                    paper_bgcolor='#0D2A2B',
                    height=360,
                    title={
                        'text': f"🔧 Top {len(available_devices) if len(available_devices) <= 5 else 5} Equipos con Prioridad de Mantenimiento",
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

def render_tab2(rsf_model, intervals, plot_devices, risk_threshold, 
                brand_dict=None, model_dict=None, df=None):
    """Renderiza la pestaña de proyección de riesgo - ORDENADO POR RIESGO ACTUAL"""
    
    # CRÍTICO: Ordenar dispositivos por riesgo actual ANTES de seleccionar top N
    features = ['total_alarms', 'alarms_last_24h', 'time_since_last_alarm_h']
    
    # Debug: Mostrar número de dispositivos antes de ordenar
    print(f"🔍 Tab 2 - Dispositivos recibidos: {len(plot_devices)}")
    
    # Ordenar por riesgo actual
    if rsf_model is not None and len(plot_devices) > 0:
        plot_devices_ordenados = ordenar_dispositivos_por_riesgo(
            rsf_model, intervals, plot_devices, features
        )
        print(f"✅ Tab 2 - Dispositivos ordenados: {len(plot_devices_ordenados)}")
        
        # Debug: Mostrar los primeros 3 con sus riesgos
        for i, device in enumerate(plot_devices_ordenados[:3]):
            riesgo = calcular_riesgo_actual(rsf_model, intervals, device, features)
            print(f"  {i+1}. {clean_device_name(device)}: {riesgo:.1f}% riesgo")
    else:
        plot_devices_ordenados = plot_devices
        print("⚠️ Tab 2 - No se pudo ordenar, usando orden original")
    
    # Slider para seleccionar cuántos equipos mostrar
    top_n = st.slider("❄️ Número de equipos a mostrar",
                      key="slider_tab2",
                      min_value=0,
                      max_value=len(plot_devices_ordenados),
                      value=min(5, len(plot_devices_ordenados)),
                      help="Selecciona cuántos de los equipos MÁS RIESGOSOS quieres visualizar")

    # Tomar los top N equipos MÁS RIESGOSOS (ya están ordenados por riesgo descendente)
    plot_devices_top = plot_devices_ordenados[:top_n]
    
    print(f"📊 Tab 2 - Mostrando top {top_n} de {len(plot_devices_ordenados)} equipos")

    if rsf_model is not None and len(plot_devices_top) > 0:
        with st.spinner("Calculando proyecciones de riesgo..."):
            # Preparar etiquetas mejoradas con marca, modelo y RIESGO ACTUAL
            device_labels = []
            device_labels_with_risk = []
            
            for device in plot_devices_top:
                _, brand, model_display = _get_device_display_info(device, df, brand_dict, model_dict)
                clean_name = clean_device_name(device)
                
                # Calcular riesgo actual para mostrar en etiqueta
                riesgo_actual = calcular_riesgo_actual(rsf_model, intervals, device, features)
                riesgo_str = f"{riesgo_actual:.1f}%" if riesgo_actual is not None else "N/A"
                
                # Crear etiqueta con riesgo actual
                if brand != "N/A" and model_display != "N/A":
                    label = f"{clean_name} ({brand} - {model_display})"
                elif brand != "N/A":
                    label = f"{clean_name} ({brand})"
                elif model_display != "N/A":
                    label = f"{clean_name} ({model_display})"
                else:
                    label = f"{clean_name}"
                
                device_labels.append(label)
                device_labels_with_risk.append((device, riesgo_actual))

            # Llamar a la función de gráfico con los dispositivos ORDENADOS
            fig = predict_failure_risk_curves(rsf_model, intervals, plot_devices_top,
                                            risk_threshold=risk_threshold,
                                            max_time=5000, device_labels=device_labels)

            fig.update_layout(
                paper_bgcolor='#113738',
                plot_bgcolor='#113738', 
                height=250,
                xaxis_title="Días desde ahora",
                yaxis_title="Probabilidad de Falla (%)",
                margin=dict(l=10, r=10, t=30, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=-1.22),
                hovermode="closest",
                xaxis=dict(range=[0, 5000 / 24], showline=True, linecolor='white', showgrid=False, zeroline=False, title_font=dict(color='white',family='Manrope'),tickfont=dict(color='white',family='Manrope')),
                yaxis=dict(
                    title_font=dict(color='white',family='Manrope'), 
                    tickfont=dict(color='white',family='Manrope'),
                    ticksuffix="%",
                    range=[0, 100]
                )
            )

            st.plotly_chart(fig, width='stretch', config={'displayModeBar': True})
    else:
        if rsf_model is None:
            st.warning("Modelo no disponible - datos insuficientes para entrenar el modelo predictivo (ver Debug).")
        else:
            st.info("No hay dispositivos para mostrar con los filtros actuales")

def render_tab3(rsf_model, intervals, df, risk_threshold, available_devices=None, 
                last_maintenance_dict=None, client_dict=None, brand_dict=None, model_dict=None):
    """Renderiza la pestaña de recomendaciones de mantenimiento - ORDENADO POR RIESGO ACTUAL"""
    if available_devices is None:
        available_devices = sorted(df['Dispositivo'].unique())
    
    if last_maintenance_dict is None:
        last_maintenance_dict = {}
    if client_dict is None:
        client_dict = {}
    if brand_dict is None:
        brand_dict = {}
    if model_dict is None:
        model_dict = {}
    
    if rsf_model is not None and len(intervals) > 0:
        features = ['total_alarms', 'alarms_last_24h', 'time_since_last_alarm_h']
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

                    serial, brand, model_display = _get_device_display_info(device, df, brand_dict, model_dict)

                    maintenance_data.append({
                        'equipo': device,
                        'equipo_clean': clean_device_name(device),
                        'serial': serial,
                        'marca': brand,
                        'modelo': model_display,
                        'tiempo_hasta_umbral': time_to_threshold,
                        'tiempo_hasta_umbral_dias': time_to_threshold / 24.0,
                        'riesgo_actual': current_risk,
                        'total_alarmas': total_alarms,
                        'tiempo_transcurrido': current_time,
                        'tiempo_transcurrido_dias': current_time / 24.0
                    })

        if maintenance_data and len(maintenance_data) > 0:
            maintenance_df_all = pd.DataFrame(maintenance_data)
            
            # ORDENAR POR RIESGO ACTUAL (DE MAYOR A MENOR) - ESTO ES NUEVO
            maintenance_df_all = maintenance_df_all.sort_values('riesgo_actual', ascending=False)
            
            maintenance_df_positive = maintenance_df_all[maintenance_df_all['tiempo_hasta_umbral'] > 0]

            if len(maintenance_df_positive) > 0:
                # Clasificar por tiempo hasta umbral pero mantener orden por riesgo dentro de cada categoría
                critico_df = maintenance_df_positive[maintenance_df_positive['tiempo_hasta_umbral_dias'] < 7]
                critico_df = critico_df.sort_values('riesgo_actual', ascending=False)

                alto_df = maintenance_df_positive[(maintenance_df_positive['tiempo_hasta_umbral_dias'] >= 7) &
                                                (maintenance_df_positive['tiempo_hasta_umbral_dias'] < 30)]
                alto_df = alto_df.sort_values('riesgo_actual', ascending=False)

                planificar_df = maintenance_df_positive[maintenance_df_positive['tiempo_hasta_umbral_dias'] >= 30]
                planificar_df = planificar_df.sort_values('riesgo_actual', ascending=False)
                
                _render_maintenance_sections(critico_df, alto_df, planificar_df, df, 
                                           last_maintenance_dict, client_dict, brand_dict, model_dict)
            else:
                st.success("✅ No hay equipos que requieran mantenimiento inmediato")
        else:
            st.info("No hay equipos con riesgo identificado para los dispositivos seleccionados")
    else:
        st.info("El modelo predictivo proporcionará recomendaciones una vez entrenado")

def _render_maintenance_sections(critico_df, alto_df, planificar_df, df, 
                               last_maintenance_dict, client_dict, brand_dict, model_dict):
    """Renderiza las secciones de mantenimiento con información de último mantenimiento, cliente y marca"""
    
    def render_device_card(row, device_failures, last_maintenance_dict, client_dict, brand_dict, model_dict, color_scheme):
        """Renderiza una tarjeta individual de dispositivo CON EXPANDER PRINCIPAL MEJORADO"""
        serial = row['serial']
        last_maintenance = last_maintenance_dict.get(serial)
        client = client_dict.get(serial, "No especificado")
        brand = row['marca']
        model_display = row['modelo']
        
        maintenance_text = format_maintenance_date(last_maintenance)
        
        # Iconos y colores según la prioridad
        priority_config = {
            'critico': {
                'icon': '❄️', 
                'colors': {'bg': '#fef2f2', 'border': '#ef4444', 'text': '#dc2626'},
                'status': 'CRÍTICO - Atención Inmediata'
            },
            'alto': {
                'icon': '❄️', 
                'colors': {'bg': '#fffbeb', 'border': '#f59e0b', 'text': '#d97706'},
                'status': 'ALTO - Planificar Pronto'
            },
            'planificar': {
                'icon': '❄️', 
                'colors': {'bg': '#f0f9ff', 'border': '#0ea5e9', 'text': '#0369a1'},
                'status': 'PLANIFICAR - Mantenimiento Programado'
            }
        }
        
        config = priority_config.get(color_scheme, priority_config['planificar'])
        color_set = config['colors']
        
        # EXPANDER PRINCIPAL con icono, estado y RIESGO ACTUAL usando nombre limpio
        with st.expander(
            f"{config['icon']} {row['equipo_clean']}", 
            expanded=False
        ):
            
            # Tarjeta de información principal
            st.markdown(f"""
            <div style='background-color: {color_set['bg']}; border-left: 5px solid {color_set['border']}; padding: 15px; margin: 10px 0; border-radius: 5px;'>
                <p style='margin: 0px 0; font-size: 12px; color:#000000;'>
                <strong>🎯 Riesgo Actual:</strong> {row['riesgo_actual']:.1f}%<br>
                <strong>🔢 Serial:</strong> {row['serial']}<br>
                <strong>🏢 Cliente:</strong> {client}<br>
                <strong>🏷️ Marca:</strong> {brand}<br>
                <strong>📋 Modelo:</strong> {model_display}<br>
                <strong>🔧 Último mantenimiento:</strong> {maintenance_text}<br>
                <strong>⏱️ Tiempo hasta umbral:</strong> {hours_to_days_hours(row['tiempo_hasta_umbral'])}<br>
                <strong>🕐 Tiempo transcurrido:</strong> {hours_to_days_hours(row['tiempo_transcurrido'])}
                </p>
            </div>
            """, unsafe_allow_html=True)

            # EXPANDER SECUNDARIO para análisis técnico
            with st.expander("🔍 Análisis Técnico y Recomendaciones", expanded=False):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.text("Fallas Detectadas")
                    if device_failures:
                        for failure in device_failures:
                            st.write(f"• {failure}")
                    else:
                        st.info("✅ No se detectaron fallas críticas")
                        
                with col2:
                    st.text("Acciones Recomendadas")
                    if device_failures:
                        recommendations = []
                        for failure in device_failures:
                            if "refrigerante" in failure.lower():
                                recommendations.extend([
                                    "• Verificar niveles de refrigerante",
                                    "• Inspeccionar posibles fugas",
                                    "• Revisar válvulas de expansión"
                                ])
                            if "compresor" in failure.lower():
                                recommendations.extend([
                                    "• Chequear motor del compresor",
                                    "• Verificar arrancadores",
                                    "• Revisar presiones de trabajo"
                                ])
                            if "humedad" in failure.lower():
                                recommendations.extend([
                                    "• Calibrar sensores de humedad",
                                    "• Limpiar bandejas de drenaje",
                                    "• Verificar filtros de aire"
                                ])
                        
                        # Eliminar duplicados
                        recommendations = list(dict.fromkeys(recommendations))
                        for rec in recommendations:
                            st.write(rec)
                    else:
                        st.write("• Limpieza general de componentes")
                        st.write("• Verificación de sistemas eléctricos")
                        st.write("• Calibración de sensores")
                        st.write("• Revisión preventiva estándar")
    
    # MANTENER LA DISTRIBUCIÓN ORIGINAL CON EXPANDERS DE PRIORIDAD Y 2 COLUMNAS POR FILA
    # PERO AHORA LOS EQUIPOS ESTÁN ORDENADOS POR RIESGO ACTUAL
    if len(critico_df) > 0:
        with st.container(key="exp-rojo"):
            with st.expander(f"🚨 **MANTENIMIENTO INMEDIATO REQUERIDO**: {len(critico_df)} equipo(s)", expanded=True):
                n_criticos = len(critico_df)
                # Crear filas de 2 columnas - equipos ya ordenados por riesgo actual
                for i in range(0, n_criticos, 2):
                    cols = st.columns(2)
                    for j in range(2):
                        if i + j < n_criticos:
                            with cols[j]:
                                row = critico_df.iloc[i + j]
                                device_failures = get_device_failures(df, row['equipo'])
                                render_device_card(row, device_failures, last_maintenance_dict, client_dict, brand_dict, model_dict, 'critico')

    if len(alto_df) > 0:
        with st.container(key="exp-amarillo"):
            with st.expander(f"⚠️ **MANTENIMIENTO PRÓXIMO**: {len(alto_df)} equipo(s)", expanded=True):
                n_altos = len(alto_df)
                # Crear filas de 2 columnas - equipos ya ordenados por riesgo actual
                for i in range(0, n_altos, 2):
                    cols = st.columns(2)
                    for j in range(2):
                        if i + j < n_altos:
                            with cols[j]:
                                row = alto_df.iloc[i + j]
                                device_failures = get_device_failures(df, row['equipo'])
                                render_device_card(row, device_failures, last_maintenance_dict, client_dict, brand_dict, model_dict, 'alto')

    if len(planificar_df) > 0:
        with st.container(key="exp-azul"):
            with st.expander(f"📅 **MANTENIMIENTO PLANIFICADO**: {len(planificar_df)} equipo(s)", expanded=True):
                n_planificar = len(planificar_df)
                # Crear filas de 2 columnas - equipos ya ordenados por riesgo actual
                for i in range(0, n_planificar, 2):
                    cols = st.columns(2)
                    for j in range(2):
                        if i + j < n_planificar:
                            with cols[j]:
                                row = planificar_df.iloc[i + j]
                                device_failures = get_device_failures(df, row['equipo'])
                                render_device_card(row, device_failures, last_maintenance_dict, client_dict, brand_dict, model_dict, 'planificar')

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