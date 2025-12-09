import requests
import urllib3
import pandas as pd
import time
from typing import List, Dict, Optional
import json
import numpy as np

# Deshabilitar advertencias de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CRMClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str):
        self.base_url = base_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expiry = None
        self.refresh_token = None
        
        # Endpoints
        self.token_url = f"{base_url}/crm/Api/access_token"
        self.equipos_url = f"{base_url}/crm/Api/V8/custom/IA/equipos-info"
        
        # Headers base
        self.base_headers = {
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json"
        }
    
    def get_access_token(self) -> bool:
        """
        Obtiene un nuevo token de acceso usando las credenciales
        Returns: True si fue exitoso, False si hubo error
        """
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        
        try:
            response = requests.post(
                self.token_url, 
                json=data, 
                headers=self.base_headers, 
                verify=False
            )
            
            if response.status_code == 200:
                tokens = response.json()
                self.access_token = tokens.get('access_token')
                #self.refresh_token = tokens.get('refresh_token')
                
                # Establecer tiempo de expiración (1 hora por defecto)
                self.token_expiry = time.time() + 3600  # 1 hora
                
                print("Token obtenido exitosamente")
                return True
            else:
                print(f"Error al obtener token: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Excepción al obtener token: {e}")
            return False
    
    def refresh_access_token(self) -> bool:
        """
        Refresca el token usando el refresh token si está disponible
        Si no, obtiene uno nuevo con credenciales
        """
        if self.refresh_token:
            # Intentar con refresh token
            data = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token
            }
            
            try:
                response = requests.post(
                    self.token_url, 
                    json=data, 
                    headers=self.base_headers, 
                    verify=False
                )
                
                if response.status_code == 200:
                    tokens = response.json()
                    self.access_token = tokens.get('access_token')
                    self.refresh_token = tokens.get('refresh_token')
                    self.token_expiry = time.time() + 3600
                    print("Token refrescado exitosamente")
                    return True
                else:
                    print(f"Error al refrescar token: {response.status_code}")
                    # Fallback: obtener nuevo token con credenciales
                    return self.get_access_token()
                    
            except Exception as e:
                print(f"Excepción al refrescar token: {e}")
                return self.get_access_token()
        else:
            # No hay refresh token, obtener uno nuevo
            return self.get_access_token()
    
    def is_token_valid(self) -> bool:
        """Verifica si el token actual es válido"""
        if not self.access_token or not self.token_expiry:
            return False
        return time.time() < self.token_expiry - 300  # 5 minutos de margen
    
    def ensure_valid_token(self) -> bool:
        """Garantiza que tenemos un token válido"""
        if not self.is_token_valid():
            print("Token expirado o no válido, obteniendo nuevo...")
            return self.refresh_access_token()
        return True
    
    def generar_variantes_serial(self, serial: str, usar_wildcards: bool = True) -> List[str]:
        """
        Genera variantes de un serial para búsqueda flexible
        
        Args:
            serial: Serial base (ej: "K2212D11349")
            usar_wildcards: Si True, agrega wildcards tipo SQL LIKE
            
        Returns:
            Lista de variantes a buscar
        """
        if not serial:
            return []
        
        serial_limpio = str(serial).strip().upper()
        variantes = []
        
        if usar_wildcards:
            # Variantes con wildcards (si el CRM las soporta)
            variantes.append(f"%{serial_limpio}%")  # Cualquier posición
            variantes.append(f"{serial_limpio}%")   # Al inicio
            variantes.append(f"%{serial_limpio}")   # Al final
        
        # Variantes sin wildcards
        variantes.append(serial_limpio)  # Exacto
        
        # Con "0" al inicio si no lo tiene
        if not serial_limpio.startswith('0'):
            variantes.append(f"0{serial_limpio}")
            if usar_wildcards:
                variantes.append(f"%0{serial_limpio}%")
        
        # Sin "0" al inicio si lo tiene
        if serial_limpio.startswith('0') and len(serial_limpio) > 1:
            sin_cero = serial_limpio[1:]
            variantes.append(sin_cero)
            if usar_wildcards:
                variantes.append(f"%{sin_cero}%")
        
        # Eliminar duplicados manteniendo orden
        return list(dict.fromkeys(variantes))
    
    def get_equipos_info(self, seriales: List[str], usar_wildcards: bool = False) -> Optional[Dict]:
        """
        Obtiene información de equipos por sus números de serie
        
        Args:
            seriales: Lista de números de serie a consultar
            usar_wildcards: Si True, genera variantes con wildcards para cada serial
            
        Returns:
            Dict con la respuesta de la API o None si hay error
        """
        if not self.ensure_valid_token():
            print("No se pudo obtener un token válido")
            return None
        
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {self.access_token}"
        
        # Convertir a lista de Python si es un array de NumPy
        if hasattr(seriales, 'tolist'):
            seriales_list = seriales.tolist()
        else:
            seriales_list = list(seriales)
        
        # Si usar_wildcards está habilitado, generar variantes
        if usar_wildcards:
            seriales_expandidos = []
            for serial in seriales_list:
                variantes = self.generar_variantes_serial(serial, usar_wildcards=True)
                seriales_expandidos.extend(variantes)
            seriales_list = seriales_expandidos
        else:
            # Solo generar variantes básicas (con/sin "0")
            seriales_expandidos = []
            for serial in seriales_list:
                variantes = self.generar_variantes_serial(serial, usar_wildcards=False)
                seriales_expandidos.extend(variantes)
            seriales_list = seriales_expandidos
        
        data = {
            "seriales": seriales_list
        }
        
        try:
            print(f"🔍 Consultando {len(seriales_list)} variantes de seriales en el CRM...")
            response = requests.post(
                self.equipos_url,
                json=data,
                headers=headers,
                verify=False
            )
            
            print(f"Respuesta HTTP: {response.status_code}")
            if response.status_code == 200:
                resultado = response.json()
                if resultado and 'data' in resultado:
                    print(f"✅ Encontrados {len(resultado['data'])} ODS en el CRM")
                return resultado
            else:
                print(f"Error en la consulta: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Excepción en la consulta: {e}")
            return None
    
    def buscar_serial_flexible(self, serial: str) -> Optional[Dict]:
        """
        Busca un serial específico usando búsqueda flexible
        Prueba primero sin wildcards, luego con wildcards si no encuentra
        
        Args:
            serial: Serial a buscar
            
        Returns:
            Dict con información del equipo o None
        """
        # Primero intentar búsqueda exacta (con variantes básicas)
        resultado = self.get_equipos_info([serial], usar_wildcards=False)
        
        if resultado and resultado.get('data'):
            return resultado
        
        # Si no encuentra, intentar con wildcards
        print(f"⚠️ No se encontró '{serial}' con búsqueda exacta, intentando con wildcards...")
        resultado = self.get_equipos_info([serial], usar_wildcards=True)
        
        return resultado
    
    def get_equipos_dataframe(self, seriales: List[str], usar_wildcards: bool = False) -> Optional[pd.DataFrame]:
        """
        Obtiene información de equipos y la convierte a DataFrame
        
        Args:
            seriales: Lista de números de serie a consultar
            usar_wildcards: Si True, usa búsqueda con wildcards
            
        Returns:
            DataFrame con la información o None si hay error
        """
        response_data = self.get_equipos_info(seriales, usar_wildcards=usar_wildcards)
        
        if response_data and 'data' in response_data:
            # Convertir a DataFrame
            df = pd.DataFrame(response_data['data'])
            
            # Normalizar nombres de columnas para incluir marca si está disponible
            expected_columns = ['serial', 'hora_salida', 'cliente', 'marca', 'modelo']
            available_columns = df.columns.tolist()
            
            print(f"📋 Columnas disponibles en respuesta CRM: {available_columns}")
            
            # Eliminar duplicados por serial (mantener el primero)
            if 'serial' in df.columns:
                df = df.drop_duplicates(subset=['serial'], keep='first')
                print(f"✅ DataFrame con {len(df)} equipos únicos")
            
            return df
        else:
            print("No se pudieron obtener datos válidos del CRM")
            return None

# Función de conveniencia para uso rápido
def crear_cliente_crm() -> CRMClient:
    """Crea y autentica un cliente CRM con las credenciales por defecto"""
    client = CRMClient(
        base_url="https://crmcotel.com.co",
        client_id="cd031831-d1f0-0a8b-b0a0-69123cd994f5",
        client_secret="Api.v8*",
    )
    
    # Obtener token inicial
    if client.get_access_token():
        print("✅ Cliente CRM creado y autenticado exitosamente")
    else:
        print("❌ Error al crear cliente CRM")
    
    return client