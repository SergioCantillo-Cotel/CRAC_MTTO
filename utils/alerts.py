import re
import pandas as pd
import numpy as np

def detect_failures(df, desc_col, sev_col=None, sev_thr=None):
    """
    Detect failures based on keywords - VERSIÓN MEJORADA basada en el nuevo código
    """
    # Palabras clave de fallas CRAC (igual que en el código nuevo)
    keywords = [
        'Low Superheat Critical', 
        'Compressor High Head Condition',
        'Returned from Idle Due To Leak Detected',
        'Compressor Drive Failure',
        "El valor de 'Humedad de suministro' (93 % RH) ha sido muy alto durante mucho tiempo",
        "El valor de 'Humedad de suministro' (94 % RH) ha sido muy alto durante mucho tiempo",
    ]

    # Palabras que indican eventos resueltos/falsos positivos
    exclude_words = ['cleared', 'corrected', 'restored', 'ok', 'normal', 'return to normal', 'solucionado']

    if desc_col not in df.columns:
        return pd.Series(False, index=df.index)

    # Buscar keywords principales y excluir los que contienen palabras de exclusión
    desc_match = (
        df[desc_col].astype(str).str.contains('|'.join(keywords), case=False, na=False) & 
        ~df[desc_col].astype(str).str.contains('|'.join(exclude_words), case=False, na=False)
    )

    # Combinar heurísticas - USAR SOLO DESCRIPCIÓN como en el código nuevo
    is_fail = desc_match
    
    return is_fail

def get_last_critical_alarm_time(df, device, sev_thr):
    """Get the timestamp of the last critical alarm for a device"""
    device_alarms = df[df['Dispositivo'] == device]
    if device_alarms.empty:
        return None
    if sev_thr is not None:
        critical_alarms = device_alarms[device_alarms['Severidad'] >= sev_thr]
    else:
        critical_alarms = device_alarms
    if len(critical_alarms) > 0:
        return critical_alarms['Fecha_alarma'].max()
    else:
        return device_alarms['Fecha_alarma'].max() if len(device_alarms) > 0 else None

def get_device_failures(df, device, desc_col='Descripcion'):
    """Get main failure types detected for a device with improved categorization"""
    device_data = df[df['Dispositivo'] == device]
    if device_data.empty:
        return []
    
    # Mapeo mejorado de fallas
    failure_mapping = {
        'Low Superheat Critical': 'Refrigerante inundando compresor - Riesgo de daño mecánico',
        'Compressor High Head Condition': 'Condición de alta presión del compresor - Sobre esfuerzo mecánico',
        'Returned from Idle Due To Leak Detected': 'Fuga de refrigerante detectada - Pérdida de capacidad de enfriamiento',
        'Compressor Drive Failure': 'Fallo en accionamiento del compresor - Problema eléctrico',
        "El valor de 'Humedad de suministro' (93 % RH) ha sido muy alto durante mucho tiempo": 'Alta humedad de suministro - Problema de control humidificador',
        "El valor de 'Humedad de suministro' (94 % RH) ha sido muy alto durante mucho tiempo": 'Alta humedad de suministro - Problema de control humidificador'
    }
    
    detected_failures = []
    desc_series = device_data[desc_col].astype(str).str.upper() if desc_col in device_data.columns else pd.Series([])
    
    for keyword, description in failure_mapping.items():
        if desc_series.str.contains(re.escape(keyword.upper()), case=False, na=False, regex=True).any():
            detected_failures.append(description)
    
    return detected_failures

def hours_to_days_hours(hours):
    """Convert hours to days and hours format with validation"""
    if pd.isna(hours) or hours is None or hours < 0:
        return "N/A"
    
    try:
        days = int(hours // 24)
        remaining_hours = int(round(hours % 24))
        
        if days == 0:
            return f"{remaining_hours}h"
        elif remaining_hours == 0:
            return f"{days}d"
        else:
            return f"{days}d {remaining_hours}h"
    except (ValueError, TypeError):
        return "N/A"