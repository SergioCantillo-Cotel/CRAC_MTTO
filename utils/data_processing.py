import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import streamlit as st
from .alerts import get_last_critical_alarm_time

def load_and_process_data(df_raw):
    """Carga y procesa los datos del DataFrame - ACTUALIZADO para BigQuery"""
    # Validación inicial
    if df_raw.empty:
        st.error("El DataFrame está vacío")
        return pd.DataFrame()
    
    df_raw.columns = [c.strip() for c in df_raw.columns]
    col_map = {}
    
    # Mapeo mejorado que incluye Serial_dispositivo
    for c in df_raw.columns:
        lc = c.lower()
        if any(x in lc for x in ['fecha', 'date', 'timestamp']) and any(x in lc for x in ['alar', 'alarm', 'evento']):
            col_map['Fecha_alarma'] = c
        elif any(x in lc for x in ['dispositivo', 'device', 'equipo', 'unit', 'asset']) and 'serial' not in lc:
            col_map['Dispositivo'] = c
        elif any(x in lc for x in ['serial', 'serie']):
            col_map['Serial_dispositivo'] = c
        elif any(x in lc for x in ['model', 'modelo']):
            col_map['Modelo'] = c
        elif any(x in lc for x in ['severidad', 'severity', 'nivel', 'level', 'priority']):
            col_map['Severidad'] = c
        elif any(x in lc for x in ['descripcion', 'description', 'mensaje', 'message', 'detail']):
            col_map['Descripcion'] = c
        elif any(x in lc for x in ['resolucion', 'resolution', 'solucion', 'clear']):
            col_map['Fecha_Resolucion'] = c

    required = ['Fecha_alarma', 'Dispositivo', 'Severidad']
    missing_cols = [r for r in required if r not in col_map]
    
    if missing_cols:
        st.error(f"Columnas necesarias no detectadas: {missing_cols}")
        st.info("Columnas disponibles en los datos:")
        st.write(list(df_raw.columns))
        return pd.DataFrame()

    df = df_raw.rename(columns={v: k for k, v in col_map.items()})

    # Procesamiento robusto de fechas
    try:
        df['Fecha_alarma'] = pd.to_datetime(df['Fecha_alarma'], errors='coerce')
        # Remover timezone de forma segura
        if df['Fecha_alarma'].dt.tz is not None:
            df['Fecha_alarma'] = df['Fecha_alarma'].dt.tz_localize(None)
    except Exception as e:
        st.error(f"Error procesando fechas de alarma: {e}")
        return pd.DataFrame()

    # Procesar fecha de resolución si existe
    if 'Fecha_Resolucion' in df.columns:
        try:
            df['Fecha_Resolucion'] = pd.to_datetime(df['Fecha_Resolucion'], errors='coerce')
            if df['Fecha_Resolucion'].dt.tz is not None:
                df['Fecha_Resolucion'] = df['Fecha_Resolucion'].dt.tz_localize(None)
        except Exception as e:
            st.warning(f"No se pudieron procesar algunas fechas de resolución: {e}")

    # Validar que hay fechas válidas
    if df['Fecha_alarma'].isna().all():
        st.error("No se pudieron procesar las fechas de alarma. Verifique el formato.")
        return pd.DataFrame()

    # Limpieza de datos
    df['Dispositivo'] = df['Dispositivo'].astype(str).str.strip()
    
    # Si existe Serial_dispositivo, también limpiarlo
    if 'Serial_dispositivo' in df.columns:
        df['Serial_dispositivo'] = df['Serial_dispositivo'].astype(str).str.strip()
    
    df['Severidad'] = pd.to_numeric(df['Severidad'], errors='coerce').fillna(0).astype(int)
    
    # Filtrar filas con datos esenciales
    initial_count = len(df)
    df = df.dropna(subset=['Fecha_alarma', 'Dispositivo']).copy()
    final_count = len(df)
    
    if initial_count != final_count:
        st.warning(f"Se removieron {initial_count - final_count} filas con datos faltantes")
    
    if df.empty:
        st.error("No quedaron datos válidos después del procesamiento")
        return pd.DataFrame()
    return df

def build_intervals_with_current_time(df, id_col, time_col, is_failure_col, sev_thr):
    """Build survival intervals from alarm data including current time"""
    df = df.sort_values([id_col, time_col]).reset_index(drop=True)
    recs = []
    now = pd.Timestamp.now().tz_localize(None)

    for unit, g in df.groupby(id_col):
        g = g.reset_index(drop=True)

        # Asegurar que los tiempos sean timezone naive
        if pd.api.types.is_datetime64_any_dtype(g[time_col]):
            try:
                times = g[time_col].dt.tz_localize(None) if g[time_col].dt.tz is not None else g[time_col]
            except Exception:
                times = pd.to_datetime(g[time_col], errors='coerce').dt.tz_localize(None)
        else:
            times = pd.to_datetime(g[time_col], errors='coerce').dt.tz_localize(None)

        times = times.to_numpy(dtype='datetime64[ns]')
        is_fail = g[is_failure_col].to_numpy(dtype=bool)
        n = len(g)
        if n == 0:
            continue

        last_critical_time = get_last_critical_alarm_time(df, unit, sev_thr)
        if last_critical_time is not None:
            last_critical_time = pd.Timestamp(last_critical_time).tz_localize(None)
            current_time_elapsed = (now - last_critical_time).total_seconds() / 3600.0
        else:
            current_time_elapsed = 0.0

        start_idx = 0
        fail_indices = np.where(is_fail)[0]

        if len(fail_indices) == 0:
            start_time = pd.Timestamp(times[start_idx])
            duration_h = (now - start_time).total_seconds() / 3600.0
            last_alarm_time = pd.Timestamp(times[-1]) if n > 0 else None
            time_since_last_alarm_h = (now - last_alarm_time).total_seconds() / 3600.0 if last_alarm_time else np.nan

            recs.append({
                'unit': unit,
                'start': start_time,
                'end': now,
                'duration_hours': float(duration_h),
                'event': 0,
                'total_alarms': int(n),
                'alarms_last_24h': 0,
                'time_since_last_alarm_h': float(time_since_last_alarm_h) if not np.isnan(time_since_last_alarm_h) else np.nan,
                'current_time_elapsed': float(current_time_elapsed),
                'last_critical_time': last_critical_time
            })
        else:
            for fi in fail_indices:
                end_idx = fi
                if end_idx <= start_idx:
                    start_idx = end_idx
                    continue

                start_time = pd.Timestamp(times[start_idx])
                end_time = pd.Timestamp(times[end_idx])
                duration_h = (end_time - start_time).total_seconds() / 3600.0
                total_alarms = end_idx - start_idx

                lookback_time = start_time - timedelta(hours=24)
                alarms_last_24h = int(np.sum((times >= np.datetime64(lookback_time)) & (times < np.datetime64(start_time))))

                last_alarm_before_idx = start_idx - 1
                if last_alarm_before_idx >= 0:
                    last_alarm_time = pd.Timestamp(times[last_alarm_before_idx])
                    time_since_last_alarm_h = (start_time - last_alarm_time).total_seconds() / 3600.0
                else:
                    time_since_last_alarm_h = np.nan

                recs.append({
                    'unit': unit,
                    'start': start_time,
                    'end': end_time,
                    'duration_hours': float(duration_h),
                    'event': 1,
                    'total_alarms': int(total_alarms),
                    'alarms_last_24h': int(alarms_last_24h),
                    'time_since_last_alarm_h': float(time_since_last_alarm_h) if not np.isnan(time_since_last_alarm_h) else np.nan,
                    'current_time_elapsed': float(current_time_elapsed),
                    'last_critical_time': last_critical_time
                })
                start_idx = end_idx

            # Censored final interval to now
            if start_idx < n:
                start_time = pd.Timestamp(times[start_idx]) if start_idx < n else pd.Timestamp(times[-1])
                duration_h = (now - start_time).total_seconds() / 3600.0
                total_alarms = n - start_idx
                lookback_time = start_time - timedelta(hours=24)
                alarms_last_24h = int(np.sum((times >= np.datetime64(lookback_time)) & (times < np.datetime64(start_time))))
                last_alarm_time = pd.Timestamp(times[-1]) if n > 0 else None
                time_since_last_alarm_h = (now - last_alarm_time).total_seconds() / 3600.0 if last_alarm_time else np.nan

                recs.append({
                    'unit': unit,
                    'start': start_time,
                    'end': now,
                    'duration_hours': float(duration_h),
                    'event': 0,
                    'total_alarms': int(total_alarms),
                    'alarms_last_24h': int(alarms_last_24h),
                    'time_since_last_alarm_h': float(time_since_last_alarm_h) if not np.isnan(time_since_last_alarm_h) else np.nan,
                    'current_time_elapsed': float(current_time_elapsed),
                    'last_critical_time': last_critical_time
                })

    return pd.DataFrame(recs)