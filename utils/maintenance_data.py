# maintenance_data.py
import pandas as pd
import streamlit as st
from datetime import datetime
from utils.api_crm import crear_cliente_crm

#@st.cache_data(ttl=3600)  # Cache por 1 hora
def load_maintenance_data(seriales,file_path='reporte_mttos.csv'):
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

def get_last_maintenance_by_serial(df_mttos):
    """
    Obtiene la fecha del último mantenimiento por cada serial
    """
    if df_mttos.empty:
        return {}
    
    try:
        # Ordenar por fecha y agrupar por serial para obtener el último mantenimiento
        last_maintenance = df_mttos.sort_values('hora_salida', ascending=False)
        last_maintenance = last_maintenance.drop_duplicates('serial', keep='first')
        
        # Crear diccionario {serial: fecha_ultimo_mantenimiento}
        maintenance_dict = dict(zip(
            last_maintenance['serial'], 
            last_maintenance['hora_salida']
        ))
        
        return maintenance_dict
        
    except Exception as e:
        st.error(f"❌ Error procesando datos de mantenimiento: {str(e)}")
        return {}

def get_client_by_serial(df_mttos):
    """
    Obtiene el cliente asociado a cada serial (si existe la columna)
    """
    if df_mttos.empty or 'cliente' not in df_mttos.columns:
        return {}
    
    try:
        # Asumimos que un serial siempre pertenece al mismo cliente
        client_mapping = df_mttos.drop_duplicates('serial', keep='first')
        client_dict = dict(zip(client_mapping['serial'], client_mapping['cliente']))
        return client_dict
        
    except Exception as e:
        st.warning(f"⚠️ No se pudo obtener información de clientes: {str(e)}")
        return {}

def format_maintenance_date(date):
    """
    Formatea la fecha de mantenimiento de manera amigable
    """
    if pd.isna(date):
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