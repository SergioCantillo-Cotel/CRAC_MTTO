# maintenance_data.py
import pandas as pd
import streamlit as st
from datetime import datetime
from utils.api_crm import crear_cliente_crm

#@st.cache_data(ttl=3600)  # Cache por 1 hora
def load_maintenance_data(seriales, file_path='reporte_mttos.csv'):
    """
    Carga y procesa los datos de mantenimiento desde el API del CRM
    """
    crm = crear_cliente_crm()
    df_mttos = crm.get_equipos_dataframe(seriales)
    
    try:
        df_mttos['serial'] = df_mttos['serial'].str.strip()
        
        # Verificar que tenemos las columnas necesarias
        required_cols = ['serial', 'hora_salida']
        missing_cols = [col for col in required_cols if col not in df_mttos.columns]
        
        if missing_cols:
            st.warning(f"⚠️ Columnas faltantes en datos de mantenimiento: {missing_cols}")
            return pd.DataFrame()
        
        # Procesar fechas
        df_mttos['hora_salida'] = pd.to_datetime(df_mttos['hora_salida'], errors='coerce')
        
        # Filtrar solo fechas válidas
        df_mttos = df_mttos.dropna(subset=['hora_salida'])
        
        if df_mttos.empty:
            st.warning("⚠️ No hay datos de mantenimiento válidos después del procesamiento")
            return pd.DataFrame()
            
        return df_mttos
        
    except Exception as e:
        st.error(f"❌ Error cargando datos de mantenimiento: {str(e)}")
        return pd.DataFrame()

def get_maintenance_metadata(df_mttos):
    """
    Obtiene todos los metadatos de mantenimiento en una sola función optimizada
    Retorna: tuple (last_maintenance_dict, client_dict, brand_dict, model_dict)
    """
    if df_mttos.empty:
        return {}, {}, {}, {}
    
    try:
        # Ordenar por fecha y agrupar por serial para obtener el último registro
        last_records = df_mttos.sort_values('hora_salida', ascending=False)
        last_records = last_records.drop_duplicates('serial', keep='first')
        
        # Crear diccionarios optimizados
        last_maintenance_dict = dict(zip(
            last_records['serial'], 
            last_records['hora_salida']
        ))
        
        client_dict = {}
        if 'cliente' in last_records.columns:
            client_dict = dict(zip(last_records['serial'], last_records['cliente']))
        
        brand_dict = {}
        if 'marca' in last_records.columns:
            brand_dict = dict(zip(last_records['serial'], last_records['marca']))

        model_dict = {}
        if 'modelo' in last_records.columns:
            model_dict = dict(zip(last_records['serial'], last_records['modelo']))
        
        return last_maintenance_dict, client_dict, brand_dict, model_dict
        
    except Exception as e:
        st.error(f"❌ Error procesando metadatos de mantenimiento: {str(e)}")
        return {}, {}, {}, {}

def get_maintenance_info_by_serial(serial, last_maintenance_dict, client_dict, brand_dict, model_dict):
    """
    Obtiene información consolidada de mantenimiento para un serial específico
    """
    return {
        'last_maintenance': last_maintenance_dict.get(serial),
        'client': client_dict.get(serial, "No especificado"),
        'brand': brand_dict.get(serial, "No especificado"),
        'model': model_dict.get(serial, "No especificado")
    }

def format_maintenance_date(date):
    """
    Formatea la fecha de mantenimiento de manera amigable
    """
    if pd.isna(date) or date is None:
        return "Nunca"
    
    try:
        # Si es una fecha reciente (últimos 30 días), mostrar "hace X días"
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

# Funciones legacy para compatibilidad (pueden ser removidas en el futuro)
def get_last_maintenance_by_serial(df_mttos):
    """Mantener para compatibilidad - usar get_maintenance_metadata en su lugar"""
    last_maintenance_dict, _, _, _ = get_maintenance_metadata(df_mttos)
    return last_maintenance_dict

def get_client_by_serial(df_mttos):
    """Mantener para compatibilidad - usar get_maintenance_metadata en su lugar"""
    _, client_dict, _, _ = get_maintenance_metadata(df_mttos)
    return client_dict