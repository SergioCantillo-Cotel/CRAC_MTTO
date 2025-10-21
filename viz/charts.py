import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import pandas as pd
from utils.model import calculate_time_to_threshold_risk

def predict_failure_risk_curves(rsf, intervals, devices, risk_threshold=0.8, max_time=5000, n_points=200):
    FEATURES = ['total_alarms', 'alarms_last_24h', 'time_since_last_alarm_h']

    fig = go.Figure()
    colors = px.colors.qualitative.Plotly

    for i, device in enumerate(devices):
        device_intervals = intervals[intervals['unit'] == device]
        if len(device_intervals) == 0:
            continue

        latest_interval = device_intervals.iloc[-1]
        feature_values = latest_interval[FEATURES].fillna(0).infer_objects(copy=False).values
        X_pred = pd.DataFrame([feature_values], columns=FEATURES)

        surv_func = rsf.predict_survival_function(X_pred)[0]

        current_time = latest_interval['current_time_elapsed']

        plot_times = np.linspace(0, max_time, n_points)
        plot_times_days = plot_times / 24.0

        adjusted_times = plot_times + current_time
        survival_probs = np.interp(adjusted_times, surv_func.x, surv_func.y, left=1.0, right=surv_func.y[-1])
        failure_risk = 1 - survival_probs

        current_risk = failure_risk[0]
        if current_risk > 0.7:
            color = '#ef4444'
        elif current_risk > 0.4:
            color = '#f59e0b'
        else:
            color = colors[i % len(colors)]

        fig.add_trace(go.Scatter(
            x=plot_times_days,
            y=failure_risk,
            mode='lines',
            name=f"{device}",
            line=dict(width=2.5, color=color),
            hovertemplate=f"Equipo: {device}<br>Tiempo desde ahora: %{{x:.1f}} días<br>Riesgo de Falla: %{{y:.3f}}<extra></extra>"
        ))

        last_critical_time = latest_interval.get('last_critical_time', None)
        time_info = f"Última alarma crítica: {pd.Timestamp(last_critical_time).strftime('%Y-%m-%d %H:%M')}" if last_critical_time is not None else "Sin alarmas críticas"
        elapsed_days = current_time / 24.0
        elapsed_info = f"Tiempo transcurrido: {elapsed_days:.1f} días"

        fig.add_trace(go.Scatter(
            x=[0],
            y=[current_risk],
            mode='markers',
            marker=dict(size=12, color=color, symbol='diamond', line=dict(width=2, color='white')),
            showlegend=False,
            name=f"{device} - Actual",
            hovertemplate=f"<b>{device}</b><br>{time_info}<br>{elapsed_info}<br>Riesgo actual: {current_risk:.3f}<extra></extra>"
        ))

        time_to_threshold, threshold_risk, _ = calculate_time_to_threshold_risk(rsf, intervals, device, risk_threshold, max_time)

        if time_to_threshold is not None and time_to_threshold <= max_time:
            threshold_x_days = time_to_threshold / 24.0
            threshold_y = threshold_risk

            fig.add_trace(go.Scatter(
                x=[threshold_x_days],
                y=[threshold_y],
                mode='markers',
                marker=dict(size=10, color=color, symbol='x', line=dict(width=2, color='black')),
                showlegend=False,
                name=f"{device} - Umbral {int(risk_threshold*100)}%",
                hovertemplate=f"<b>{device}</b><br>Tiempo hasta {int(risk_threshold*100)}% riesgo: {threshold_x_days:.1f} días<br>Riesgo: {threshold_risk:.3f}<extra></extra>"
            ))

    fig.add_hline(
        y=risk_threshold,
        line_dash="dash",
        line_color="red",
    )

    fig.update_layout(
        font=dict(family="Poppins", color="black"),
        height=700,  # Altura fija para evitar crecimiento excesivo
        legend=dict(
            orientation="v",  # Leyenda vertical
            yanchor="top",
            xanchor="left",
            font=dict(size=10.5,family='Poppins'),  # Tamaño de fuente reducido
            itemwidth=30,  # Ancho consistente para items
            borderwidth=1,
            tracegroupgap=8,
            itemclick="toggle",
            itemdoubleclick="toggleothers"
        ),
        xaxis=dict(showline=True, linecolor='black', showgrid=False, zeroline=False, title_font=dict(color='black',family='Poppins'),tickfont=dict(color='black',family='Poppins')),
        yaxis=dict(domain=[0.00, 1.00],title_font=dict(color='black',family='Poppins'), tickfont=dict(color='black',family='Poppins')),
        
        margin=dict(l=50, r=150, t=0, b=50),  # Margen derecho amplio para leyenda
        plot_bgcolor='white',
        paper_bgcolor='white'
    )

    return fig