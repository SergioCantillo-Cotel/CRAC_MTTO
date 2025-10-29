import streamlit as st
from streamlit_autorefresh import st_autorefresh
from google.oauth2 import service_account
from google.cloud import bigquery
from datetime import datetime, timedelta
import pandas as pd
import time

EQUIPO_SERIAL_MAPPING = {
    # FANALCA
    "FANALCA - AIRE APC 1": "JK1142005099",
    "FANALCA - AIRE APC 2": "JK2117000712", 
    "FANALCA - AIRE APC 3": "JK2117000986",
    
    # SPIA
    "SPIA-A.A#1": "SCA131150",
    "SPIA-A.A#2": "SCA131148",
    "SPIA-A.A#3": "SCA131149",
    
    # EAFIT
    "EAFIT-Bloque 18-1-Direccion Informatica": "UCV101363",
    "EAFIT-Bloque 18-2-Direccion Informatica": "UCV105388",
    "EAFIT-Bloque 19-1-Centro de Computo APOLO": "JK1821004033",
    "EAFIT - Bloque 19 - 2 - Centro de Computo APOLO": "JK1831002840",
    
    # Metro Talleres y PCC
    "Metro Talleres - Aire 1": "UK1008210542",
    "Metro Talleres - Aire 2": "JK16400002252",
    "Metro Talleres - Aire 3": "JK1905003685",
    "Metro PCC - Aire Rack 4": "JK1213009088",
    "Metro PCC - Aire Giax 5": "2016-1091A",
    "Metro PCC - Aire Gfax 8": "2016-1094A",
    
    # UTP
    "UTP-AIRE 1 Datacenter": "JK2147003126",
    "UTP-AIRE 2 Datacenter": "JK2147003130",
    "UTP-AIRE 3 Datacenter": "JK2230004923",
    
    # UNICAUCA
    "UNICAUCA-AIRE 1-PASILLO A": "JK1923002790",
    "UNICAUCA-AIRE 2-PASILLO B": "JK1743000230",
    "UNICAUCA-AIRE 3-PASILLO A": "JK1811002605",
    "UNICAUCA-AIRE 4-PASILLO B": "JK1923002792"
}

def bigquery_auth():
    """Autenticación con BigQuery usando secrets de Streamlit"""
    try:
        credenciales_info = {
            "type": st.secrets["gcp_service_account"]["type"],
            "project_id": st.secrets["gcp_service_account"]["project_id"],
            "private_key_id": st.secrets["gcp_service_account"]["private_key_id"],
            "private_key": st.secrets["gcp_service_account"]["private_key"].replace('\\n', '\n'),
            "client_email": st.secrets["gcp_service_account"]["client_email"],
            "client_id": st.secrets["gcp_service_account"]["client_id"],
            "auth_uri": st.secrets["gcp_service_account"]["auth_uri"],
            "token_uri": st.secrets["gcp_service_account"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gcp_service_account"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["gcp_service_account"]["client_x509_cert_url"]
        }
        
        credentials = service_account.Credentials.from_service_account_info(credenciales_info)
        return credentials
    except Exception as e:
        st.error(f"Error en autenticación BigQuery: {str(e)}")
        return None

def read_bq_alarms_safe(credentials, days_back=180):
    """
    Consulta segura a BigQuery - sin filtros complejos
    """
    if credentials is None:
        return pd.DataFrame()
    
    try:
        BIGQUERY_PROJECT_ID = st.secrets["gcp_service_account"]["project_id"]
        client = bigquery.Client(project=BIGQUERY_PROJECT_ID, credentials=credentials)
        
        # Consulta mínima y segura
        sql_query = """
        SELECT
          FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', t1.alarm_date) AS Fecha_alarma,
          t2.serial_number_device AS Serial_dispositivo,
          t2.name_device AS Dispositivo,
          FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', t1.alarm_resolution_date) AS Fecha_Resolucion,
          t1.description_alarm AS Descripcion,
          t1.severity AS Severidad
        FROM
          `eficiencia-energetica-427815.integracion_dce_monitoreo_clientes_cotel.alarmas` AS t1
        INNER JOIN
          `eficiencia-energetica-427815.integracion_dce_monitoreo_clientes_cotel.dispositivos` AS t2
        ON
          t1.device_id = t2.id_device
        WHERE
          LOWER(t2.type_device) = 'cooling device'
        ORDER BY
          t1.alarm_date
        """
        
        query_job = client.query(sql_query)
        results = query_job.result()
        
        data = []
        for row in results:
            data.append({
                'Fecha_alarma': row['Fecha_alarma'],
                'Serial_dispositivo': row['Serial_dispositivo'],
                'Dispositivo': row['Dispositivo'],
                'Fecha_Resolucion': row['Fecha_Resolucion'] if row['Fecha_Resolucion'] else None,
                'Descripcion': row['Descripcion'],
                'Severidad': row['Severidad']
            })
        
        df = pd.DataFrame(data)
        
        if not df.empty:
            # Procesar fechas
            df['Fecha_alarma'] = pd.to_datetime(df['Fecha_alarma'])
            if 'Fecha_Resolucion' in df.columns:
                df['Fecha_Resolucion'] = pd.to_datetime(df['Fecha_Resolucion'], errors='coerce')
            
            # Filtrar por fecha localmente
            cutoff_date = datetime.now() - timedelta(days=days_back)
            df = df[df['Fecha_alarma'] >= cutoff_date].copy()
            
        return df
            
    except Exception as e:
        st.error(f"Error al consultar los datos: {str(e)}")
        return pd.DataFrame()


def completar_seriales_faltantes(df, nombre_columna='Dispositivo', serial_columna='Serial_dispositivo'):
    """
    Completa los seriales faltantes en el DataFrame basado en el mapeo de equipos
    """
    # Crear columna de serial si no existe
    if serial_columna not in df.columns:
        df[serial_columna] = None
    
    def buscar_serial(nombre_equipo):
        if pd.isna(nombre_equipo):
            return None
        
        nombre_equipo = str(nombre_equipo).strip()
        
        # Búsqueda exacta
        if nombre_equipo in EQUIPO_SERIAL_MAPPING:
            return EQUIPO_SERIAL_MAPPING[nombre_equipo]
        
        # Búsqueda flexible
        for key, value in EQUIPO_SERIAL_MAPPING.items():
            if nombre_equipo in key or key in nombre_equipo:
                return value
        
        return None
    
    # Aplicar la función
    df[serial_columna] = df.apply(
        lambda row: row[serial_columna] if pd.notna(row[serial_columna]) else buscar_serial(row[nombre_columna]),
        axis=1
    )
    
    return df

def autorefresh(key: str = "q", state_key: str = "first", time: int = 10) -> None:
    """Refresca en el próximo múltiplo de 10 minutos."""
    ms_to_q = lambda: ((time - datetime.now().minute % time) * 60 - datetime.now().second) * 1000 - datetime.now().microsecond // 1000
    first = st.session_state.setdefault(state_key, True)
    interval = ms_to_q() if first else time * 60 * 1000
    st.session_state[state_key] = False
    st_autorefresh(interval=interval, key=key)
