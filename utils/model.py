
import warnings
import numpy as np
import pandas as pd
from sksurv.ensemble import RandomSurvivalForest
from sksurv.util import Surv
from sklearn.impute import SimpleImputer
import streamlit as st

def train_rsf_model(intervals):
    """Train Random Survival Forest model with enhanced parameters"""
    FEATURES = ['total_alarms', 'alarms_last_24h', 'time_since_last_alarm_h']
    
    # Usar parámetros mejorados basados en el nuevo código
    RSF_PARAMS = {
        "n_estimators": 250,  # Aumentado de 100 a 250
        "max_features": "sqrt",
        "n_jobs": -1,
        "random_state": 42
    }

    # Validaciones (mantener las existentes)
    if len(intervals) == 0:
        raise ValueError("No hay intervalos para entrenar el modelo.")

    missing_features = [f for f in FEATURES if f not in intervals.columns]
    if missing_features:
        raise ValueError(f"Faltan características necesarias: {missing_features}")

    # Preparar características
    X_df = intervals[FEATURES].copy()
    
    # Imputar valores faltantes
    imputer = SimpleImputer(strategy='median')
    X_imputed = imputer.fit_transform(X_df)
    X_df = pd.DataFrame(X_imputed, columns=FEATURES, index=X_df.index)
    
    # Validar eventos y tiempos
    events = intervals['event'].astype(bool).to_numpy()
    times = intervals['duration_hours'].to_numpy()

    n_samples = len(events)
    n_events = int(np.sum(events))

    # Validaciones críticas
    if n_events == 0:
        raise ValueError(f"No se puede entrenar RSF: todos los {n_samples} samples están censurados (0 eventos).")

    if n_events < 3:
        raise ValueError(f"Muy pocos eventos ({n_events}) para entrenar modelo confiable. Mínimo requerido: 3")

    if n_samples < 10:
        raise ValueError(f"Muy pocas muestras ({n_samples}) para entrenar modelo confiable.")

    # Verificar variabilidad en tiempos
    if np.std(times) == 0:
        raise ValueError("No hay variabilidad en los tiempos de supervivencia.")

    try:
        y = Surv.from_arrays(event=events, time=times)
        rsf = RandomSurvivalForest(**RSF_PARAMS)
        rsf.fit(X_df, y)
        
        # Validación rápida del modelo
        train_scores = rsf.score(X_df, y)
        if train_scores < 0.5:
            warnings.warn(f"El modelo tiene bajo concordance index en entrenamiento: {train_scores:.3f}")
            
        return rsf, FEATURES
        
    except Exception as e:
        raise ValueError(f"Error entrenando el modelo RSF: {str(e)}")

def calculate_time_to_threshold_risk(rsf, intervals, device, risk_threshold=0.8, max_time=5000):
    FEATURES = ['total_alarms', 'alarms_last_24h', 'time_since_last_alarm_h']
    
    if device not in intervals['unit'].values:
        return None, None, None

    device_intervals = intervals[intervals['unit'] == device]
    if len(device_intervals) == 0:
        return None, None, None

    latest_interval = device_intervals.iloc[-1]
    
    # Validar características
    feature_values = []
    for feature in FEATURES:
        if feature in latest_interval:
            val = latest_interval[feature]
            feature_values.append(0.0 if pd.isna(val) else float(val))
        else:
            feature_values.append(0.0)
    
    X_pred = pd.DataFrame([feature_values], columns=FEATURES)

    try:
        surv_funcs = rsf.predict_survival_function(X_pred)
        if len(surv_funcs) == 0:
            return None, None, None
            
        surv_func = surv_funcs[0]
        current_time = float(latest_interval.get('current_time_elapsed', 0))

        # Buscar punto donde se alcanza el umbral de riesgo
        time_points = np.linspace(current_time, current_time + max_time, 500)
        
        for time_point in time_points:
            survival_prob = np.interp(time_point, surv_func.x, surv_func.y, 
                                    left=1.0, right=surv_func.y[-1])
            risk = 1 - survival_prob
            if risk >= risk_threshold:
                time_to_threshold = time_point - current_time
                return time_to_threshold, risk, current_time

        # Si no se alcanza el umbral en el tiempo máximo
        final_risk = 1 - np.interp(current_time + max_time, surv_func.x, surv_func.y, 
                                 left=1.0, right=surv_func.y[-1])
        return max_time, final_risk, current_time
        
    except Exception as e:
        st.warning(f"Error calculando riesgo para {device}: {str(e)}")
        return None, None, None

@st.cache_resource(show_spinner="Entrenando modelo predictivo de fallas...")
def build_rsf_model(_df, sev_thr):
    """Build RSF model con umbral de severidad fijo - CON CACHING GLOBAL"""
    from utils.alerts import detect_failures
    from utils.data_processing import build_intervals_with_current_time
    
    try:
        df_processed = _df.copy()
        
        # Detectar fallas usando la función mejorada
        desc_col = 'Descripcion' if 'Descripcion' in df_processed.columns else 'Dispositivo'
        df_processed['is_failure_bool'] = detect_failures(
            df_processed,
            desc_col,
            'Severidad',
            sev_thr=sev_thr  # Usar el umbral fijo
        )

        # Construir intervalos
        intervals = build_intervals_with_current_time(
            df_processed,
            'Dispositivo',
            'Fecha_alarma',
            'is_failure_bool',
            sev_thr  # Usar el umbral fijo
        )

        if intervals.empty:
            st.warning("No se generaron intervalos válidos. Verifique los datos y el umbral de severidad.")
            return None, pd.DataFrame(), None

        # Estadísticas para debug
        n_events = int(intervals['event'].sum())
        n_samples = len(intervals)
        
        #st.info(f"📊 Estadísticas del modelo: {n_samples} intervalos, {n_events} eventos de falla")
        #st.info(f"⚙️ Umbral de severidad configurado: {sev_thr}")

        # Condiciones para entrenamiento
        if n_samples >= 10 and n_events >= 3:
            try:
                rsf_model, features = train_rsf_model(intervals)
                #st.success("✅ Modelo entrenado exitosamente")
                return rsf_model, intervals, features
            except ValueError as e:
                st.warning(f"⚠️ No se pudo entrenar el modelo: {str(e)}")
                return None, intervals, None
            except Exception as e:
                st.error(f"❌ Error inesperado entrenando modelo: {str(e)}")
                return None, intervals, None
        else:
            if n_samples < 10:
                st.warning(f"⚠️ Datos insuficientes: {n_samples} intervalos (mínimo 10 requeridos)")
            if n_events < 3:
                st.warning(f"⚠️ Eventos insuficientes: {n_events} fallas detectadas (mínimo 3 requeridas)")
            return None, intervals, None
            
    except Exception as e:
        st.error(f"❌ Error crítico construyendo modelo: {str(e)}")
        return None, pd.DataFrame(), None
