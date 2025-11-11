import streamlit as st
import os

def load_custom_css(file_path: str = "styles/style.css"):
    try:
        # Intentar con UTF-8 primero, luego con otras codificaciones
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    css_content = f.read()
                st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
                return
            except UnicodeDecodeError:
                continue
            except FileNotFoundError:
                st.error(f"❌ Archivo CSS no encontrado: {file_path}")
                return
        
        # Si todas las codificaciones fallan, intentar modo binario
        with open(file_path, 'rb') as f:
            raw_content = f.read()
            # Intentar decodificar ignorando errores
            css_content = raw_content.decode('utf-8', errors='ignore')
            st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
            
    except Exception as e:
        st.error(f"❌ Error cargando CSS: {str(e)}")