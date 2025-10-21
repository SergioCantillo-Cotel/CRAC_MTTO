import streamlit as st
from streamlit_autorefresh import st_autorefresh
from google.oauth2 import service_account
from google.cloud import bigquery
from datetime import datetime, timedelta
import pandas as pd
import time

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
        st.error(f"Error en consulta BigQuery: {str(e)}")
        return pd.DataFrame()

def autorefresh(key: str = "q", state_key: str = "first", time: int = 10) -> None:
    """Refresca en el próximo múltiplo de 10 minutos."""
    ms_to_q = lambda: ((time - datetime.now().minute % time) * 60 - datetime.now().second) * 1000 - datetime.now().microsecond // 1000
    first = st.session_state.setdefault(state_key, True)
    interval = ms_to_q() if first else time * 60 * 1000
    st.session_state[state_key] = False
    st_autorefresh(interval=interval, key=key)
