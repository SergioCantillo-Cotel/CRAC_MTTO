# maintenance_data.py
import pandas as pd
import streamlit as st
from datetime import datetime
from utils.api_crm import crear_cliente_crm

def normalizar_serial(serial):
    """
    Normaliza un serial para comparación flexible.
    Permite que coincidan seriales con o sin "0" al inicio.
    
    Ejemplos:
        "0K2212D11349" → "K2212D11349"
        "K2212D11349"  → "K2212D11349"
    """
    if pd.isna(serial) or serial is None:
        return None
    
    serial_str = str(serial).strip().upper()
    
    # Remover "0" inicial si existe
    if serial_str.startswith('0') and len(serial_str) > 1:
        serial_str = serial_str[1:]
    
    return serial_str

#@st.cache_data(ttl=3600)  # Cache por 1 hora
def load_maintenance_data(seriales, file_path='reporte_mttos.csv'):
    """
    Carga y procesa los datos de mantenimiento desde el API del CRM
    Usa búsqueda flexible con wildcards si el CRM lo soporta
    """
    crm = crear_cliente_crm()
    
    # Normalizar seriales antes de buscar
    seriales_normalizados = [normalizar_serial(s) for s in seriales if s is not None]
    seriales_normalizados = list(set([s for s in seriales_normalizados if s]))  # Eliminar None y duplicados
    
    if not seriales_normalizados:
        return pd.DataFrame()
    
    # Intentar primero con búsqueda flexible (genera variantes automáticamente)
    # El parámetro usar_wildcards=False genera variantes con/sin "0" pero sin "%"
    # Si el CRM soporta wildcards, cambiar a usar_wildcards=True
    df_mttos = crm.get_equipos_dataframe(seriales_normalizados, usar_wildcards=False)
    
    if df_mttos is None or df_mttos.empty:
        print("⚠️ No se encontraron datos en el CRM con búsqueda estándar")
        print("🔍 Intentando con búsqueda flexible (wildcards)...")
        # Intentar con wildcards si el CRM lo soporta
        df_mttos = crm.get_equipos_dataframe(seriales_normalizados, usar_wildcards=True)
    
    if df_mttos is None or df_mttos.empty:
        print("❌ No se encontraron datos de mantenimiento en el CRM")
        return pd.DataFrame()
    
    if df_mttos is None or df_mttos.empty:
        return pd.DataFrame()
    
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
    Obtiene todos los metadatos de mantenimiento en una sola función optimizada.
    Usa normalización de seriales para coincidencias flexibles.
    Retorna: tuple (last_maintenance_dict, client_dict, brand_dict, model_dict)
    """
    if df_mttos.empty:
        return {}, {}, {}, {}
    
    try:
        # Ordenar por fecha y agrupar por serial para obtener el último registro
        last_records = df_mttos.sort_values('hora_salida', ascending=False)
        last_records = last_records.drop_duplicates('serial', keep='first')
        
        # Crear diccionarios con AMBAS versiones del serial (con y sin "0")
        last_maintenance_dict = {}
        client_dict = {}
        brand_dict = {}
        model_dict = {}
        
        for _, row in last_records.iterrows():
            serial_original = row['serial']
            serial_normalizado = normalizar_serial(serial_original)
            
            # Datos a guardar
            fecha = row['hora_salida']
            cliente = row.get('cliente', 'No especificado')
            marca = row.get('marca', 'No especificado')
            modelo = row.get('modelo', 'No especificado')
            
            # Guardar con AMBAS versiones del serial
            # Versión original (ej: "0K2212D11349")
            last_maintenance_dict[serial_original] = fecha
            client_dict[serial_original] = cliente
            brand_dict[serial_original] = marca
            model_dict[serial_original] = modelo
            
            # Versión normalizada (ej: "K2212D11349")
            if serial_normalizado and serial_normalizado != serial_original:
                last_maintenance_dict[serial_normalizado] = fecha
                client_dict[serial_normalizado] = cliente
                brand_dict[serial_normalizado] = marca
                model_dict[serial_normalizado] = modelo
                
                # También versión con "0" si no lo tiene
                if not serial_original.startswith('0'):
                    serial_con_cero = '0' + serial_normalizado
                    last_maintenance_dict[serial_con_cero] = fecha
                    client_dict[serial_con_cero] = cliente
                    brand_dict[serial_con_cero] = marca
                    model_dict[serial_con_cero] = modelo
        
        return last_maintenance_dict, client_dict, brand_dict, model_dict
        
    except Exception as e:
        st.error(f"❌ Error procesando metadatos de mantenimiento: {str(e)}")
        return {}, {}, {}, {}

def get_maintenance_info_by_serial(serial, last_maintenance_dict, client_dict, brand_dict, model_dict):
    """
    Obtiene información consolidada de mantenimiento para un serial específico.
    Usa normalización para buscar con flexibilidad.
    """
    # Buscar con el serial original
    info = {
        'last_maintenance': last_maintenance_dict.get(serial),
        'client': client_dict.get(serial, "No especificado"),
        'brand': brand_dict.get(serial, "No especificado"),
        'model': model_dict.get(serial, "No especificado")
    }
    
    # Si no se encontró con el serial original, buscar con versión normalizada
    if info['last_maintenance'] is None:
        serial_normalizado = normalizar_serial(serial)
        if serial_normalizado:
            info = {
                'last_maintenance': last_maintenance_dict.get(serial_normalizado),
                'client': client_dict.get(serial_normalizado, "No especificado"),
                'brand': brand_dict.get(serial_normalizado, "No especificado"),
                'model': model_dict.get(serial_normalizado, "No especificado")
            }
    
    # Si aún no se encontró, intentar con "0" al inicio
    if info['last_maintenance'] is None and serial and not serial.startswith('0'):
        serial_con_cero = '0' + serial
        info = {
            'last_maintenance': last_maintenance_dict.get(serial_con_cero),
            'client': client_dict.get(serial_con_cero, "No especificado"),
            'brand': brand_dict.get(serial_con_cero, "No especificado"),
            'model': model_dict.get(serial_con_cero, "No especificado")
        }
    
    return info

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