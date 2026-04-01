import streamlit as st
from supabase import create_client, Client
from datetime import datetime

# --- CONFIGURAÇÃO DE CONEXÃO SUPABASE ---
# Certifique-se de que não haja espaços antes ou depois das aspas
SUPABASE_URL = "https://oqmeyhkyxuprubwqcwuj.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9xbWV5aGt5eHVwcnVid3Fjd3VqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM4NjU3ODMsImV4cCI6MjA4OTQ0MTc4M30.ALFqZ0DjhJNQ2mxkS9mZvaN_8dyBuqlEB74omH2iI7U"

@st.cache_resource
def init_connection():
    """
    Inicializa a conexão única com o Supabase. 
    O cache_resource evita que o Streamlit abra uma nova conexão a cada refresh,
    prevenindo erros de DNS/Rede (getaddrinfo failed).
    """
    try:
        # Validação básica de preenchimento
        if "sua-url" in SUPABASE_URL or not SUPABASE_URL:
            st.error("⚠️ URL do Supabase não configurada no orcas_v01_security.py")
            return None
            
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"Erro ao estabelecer conexão com o servidor: {e}")
        return None

# Instância global para ser importada pelo orcasapp.py
# via 'from orcas_v01_security import supabase'
supabase: Client = init_connection()

# --- REGRAS DE ACESSO E SEGURANÇA ---

def verificar_bloqueio_v01(uid, dias_rest):
    """
    Verifica a validade da assinatura.
    Se o atraso for maior que 5 dias (dias_rest < -5), trava o sistema.
    """
    if dias_rest < -5:
        st.markdown(f"""
            <div style="background-color: #fee2e2; padding: 20px; border-radius: 10px; border: 2px solid #ef4444; margin: 10px 0;">
                <h2 style="color: #b91c1c; margin-top: 0;">🐋 ORCAS: Acesso Bloqueado</h2>
                <p style="color: #7f1d1d;">Seu período de uso ou assinatura expirou.</p>
                <hr style="border: 0; border-top: 1px solid #fecaca;">
                <p style="font-weight: bold; color: #b91c1c;">Contato para liberação: financeiro@orcas.com</p>
            </div>
        """, unsafe_allow_html=True)
        st.stop() # Interrompe a execução do script principal imediatamente

# --- REGRAS DE NEGÓCIO E CÁLCULOS ---

def calcular_valor_v01(num_projetos, data_ini, data_fim):
    """
    Calcula o valor da mensalidade baseada no uso do SaaS.
    Regra atual: R$ 29,90 por fluxo (projeto) ativo.
    """
    try:
        # Garante que pelo menos 1 projeto seja contabilizado na base
        quantidade = max(1, num_projetos)
        valor_total = quantidade * 29.90
        return valor_total
    except Exception:
        # Retorno padrão para evitar quebra de interface caso o cálculo falhe
        return 29.90

def validar_sessao_v01():
    """Valida se os dados de login estão presentes no estado da sessão."""
    check = all(k in st.session_state for k in ['logado', 'user_id', 'usuario'])
    return check and st.session_state.logado

# --- FIM DO ARQUIVO SECURITY ---