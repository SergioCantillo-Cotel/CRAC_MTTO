# auth_config.py
import streamlit as st
import hashlib
import hmac

# Configuración de usuarios (en producción, usa una base de datos)
USERS = {
    "admin": {
        "password": "admin123!",  # Cambia esta contraseña
        "name": "",
        "role": "Administrador",
        "cliente": "Todos los clientes"
    },
    "EAFIT": {
        "password": "EAFIT1!",  # Cambia esta contraseña
        "name": "EAFIT",
        "role": "Operador",
        "cliente": "UNIVERSIDAD EAFIT"
    },
    "UNICAUCA": {
        "password": "UCA1!",  # Cambia esta contraseña
        "name": "UNICAUCA",
        "role": "Operador",
        "cliente": "UNIVERSIDAD DEL CAUCA"
    }
}

def hash_password(password):
    """Hashea la contraseña para comparación segura"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_login(username, password):
    """Verifica las credenciales del usuario"""
    if username in USERS:
        stored_password = USERS[username]["password"]
        # Comparación segura de contraseñas
        return hmac.compare_digest(
            hash_password(password), 
            hash_password(stored_password)
        )
    return False

def init_session_state():
    """Inicializa el estado de la sesión"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'username' not in st.session_state:
        st.session_state.username = None
    if 'user_info' not in st.session_state:
        st.session_state.user_info = None

def render_sidebar_login():
    """Renderiza el formulario de login en el sidebar"""
    st.sidebar.markdown("""
        <style>
        .login-form-container {
            margin-top: 0rem;
        }
        </style>
    """, unsafe_allow_html=True)

    st.sidebar.markdown('### 🔐 Inicia sesión')
    st.sidebar.markdown('Accede a tus dashboards, alertas y reportes.')
    
    st.sidebar.markdown('<div class="login-form-container">', unsafe_allow_html=True)
    with st.sidebar.form("sidebar_login_form"):
        username = st.text_input("👤 **Usuario**", placeholder="Ingresa tu usuario", key="input-user")
        password = st.text_input("🔒 **Contraseña**", type="password", placeholder="Ingresa tu contraseña",key='input-pass')

        # Checkbox de "Recordar contraseña" (solo visual por ahora)
        #remember_me = st.checkbox("Recordar contraseña")
        
        submit = st.form_submit_button("**Ingresar**", use_container_width=True, key="login_btn")
        
        if submit:
            if verify_login(username, password):
                st.session_state.authenticated = True
                st.session_state.username = username
                st.session_state.user_info = USERS[username]
                st.rerun()
            else:
                st.toast("Usuario o contraseña incorrectos",icon='❌',duration=4)
    
    st.sidebar.markdown("</div>", unsafe_allow_html=True)
    st.sidebar.markdown("</div>", unsafe_allow_html=True)

def render_sidebar_user_info():
    """Renderiza la información del usuario en el sidebar de forma amigable"""
    if st.session_state.authenticated and st.session_state.user_info:
        user_info = st.session_state.user_info
        
        # Expander con el saludo como título y el logout dentro
        with st.sidebar.expander(f"👋 Hola, **{st.session_state.username}**", expanded=False):
            st.markdown(f"**🎯 Rol:** {user_info['role']}")
            st.markdown(f"**🏢 Cliente:** {user_info['cliente']}")
            
            # Botón de logout dentro del expander
            if st.button("🚪 **Cerrar Sesión**", use_container_width=True, key="logout_btn"):
                st.session_state.authenticated = False
                st.session_state.username = None
                st.session_state.user_info = None
                st.rerun()

def require_auth():
    """Verifica si el usuario está autenticado"""
    return st.session_state.get('authenticated', False)

def get_current_user():
    """Obtiene información del usuario actual"""
    if st.session_state.authenticated:
        return st.session_state.user_info
    return None