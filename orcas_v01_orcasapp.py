import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import hashlib
import plotly.graph_objects as go
import streamlit.components.v1 as components
from supabase import Client
from streamlit_js_eval import streamlit_js_eval

# --- 1. IMPORTAÇÃO DOS MÓDULOS EXTERNOS ---
import orcas_v01_gestao as gestao
import orcas_v01_dashboard as dash
import orcas_v01_lancamentos as lanc
import orcas_v01_projetar as proj
import orcas_v01_conciliacao as conc
import orcas_v01_admin as adm

# --- 2. SEGURANÇA E CONEXÃO ---
try:
    import orcas_v01_security as security
    supabase: Client = security.supabase
except Exception as e:
    st.error(f"Erro de conexão: Verifique o arquivo security.py. {e}")
    st.stop()

# --- 3. CONFIGURAÇÃO E ESTILO ---

# INOVAÇÃO: Controle de estado da Sidebar via Session State
if 'estado_sidebar' not in st.session_state:
    st.session_state.estado_sidebar = "expanded"

st.set_page_config(
    page_title="ORCAS - Gestão Financeira", 
    page_icon="🐋", 
    layout="wide", 
    initial_sidebar_state=st.session_state.estado_sidebar
)

def ir_para_o_topo():
    components.html("""<script>window.parent.document.getElementById('topo-ancora').scrollIntoView();</script>""", height=0)

st.markdown("""
    <style>
    /* Oculta menus nativos e footer */
    #MainMenu {visibility: hidden;} 
    footer {visibility: hidden;}
    .stAppDeployButton {display:none !important;}
    [data-testid="stStatusWidget"] {display:none !important;}
    
    /* Cabeçalho e Botões >> e << */
    [data-testid="stHeader"] {
        background-color: rgba(0,0,0,0) !important;
    }
    
    /* Remove badges flutuantes do canto inferior direito */
    [data-testid="stDecoration"],
    .viewerBadge_container__1QSob,
    .viewerBadge_link__1S137,
    div[class*="stDecoration"] {
        display: none !important;
        visibility: hidden !important;
    }

    /* Ajuste de altura para conteúdo */
    .block-container {
        padding-top: 3.0rem !important;
        margin-top: -1.5rem !important;
    }

    /* Estilos customizados ORCAS */
    .logo-sidebar { font-size: 2.2rem !important; font-weight: bold; color: #1E3A8A; font-family: 'Arial Black', sans-serif; margin-bottom: 20px; }
    .user-email { font-size: 0.85rem; color: #64748b; margin-bottom: 2px; }
    .venc-text { font-size: 0.8rem; color: #e11d48; font-weight: bold; margin-bottom: 10px; }
    .titulo-tela { font-size: 1.6rem; font-weight: bold; color: #1E3A8A; border-bottom: 2px solid #E5E7EB; margin-bottom: 15px; padding-bottom: 5px; }
    .project-tag-sidebar { color: #1E3A8A; font-weight: bold; font-size: 0.9rem; margin-bottom: 15px; padding: 8px; border-left: 5px solid #1E3A8A; background: #F3F4F6; border-radius: 4px; }
    </style>
""", unsafe_allow_html=True)

def format_moeda(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def parse_moeda(t):
    try:
        t = str(t).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        return float(t)
    except:
        return 0.0

# --- 4. LOGIN ---
if 'logado' not in st.session_state:
    st.session_state.logado = False

if not st.session_state.logado:
    st.markdown("<h1 style='text-align: center; margin-top: 50px;'>🐋 ORCAS</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        aba = st.tabs(["Acessar Conta", "Criar Nova Conta"])
        with aba[0]:
            em = st.text_input("E-mail Cadastrado")
            se = st.text_input("Senha de Acesso", type="password")
            col_btn_l1, col_btn_l2 = st.columns(2)
            if col_btn_l1.button("Entrar no Sistema"):
                senha_hash = hashlib.sha256(str.encode(se)).hexdigest()
                res = supabase.table("usuarios").select("id, vencimento, zap_ativo").eq("email", em).eq("senha", senha_hash).execute()
                if res.data: 
                    user_data = res.data[0]
                    st.session_state.logado = True
                    st.session_state.CHAVE_MESTRA_UUID = str(user_data['id'])
                    st.session_state.usuario = em
                    st.session_state.vencimento = str(user_data['vencimento'])
                    st.session_state.zap_ativo = user_data.get('zap_ativo', 0)
                    st.session_state.projeto_ativo = None
                    st.rerun()
                else:
                    st.error("E-mail ou senha incorretos.")
            if col_btn_l2.button("Esqueci minha Senha"):
                st.info("Entre em contato com o suporte administrativo.")
    st.stop()

# --- 5. ESTADO E DADOS ---
ID_USUARIO_LOGADO = str(st.session_state.get('CHAVE_MESTRA_UUID', ''))
vencimento_str = st.session_state.get('vencimento', '2026-01-01')
venc_dt_objeto = datetime.strptime(vencimento_str, '%Y-%m-%d').date()

if ID_USUARIO_LOGADO:
    security.verificar_bloqueio_v01(ID_USUARIO_LOGADO, (venc_dt_objeto - datetime.now().date()).days)

projs_req = supabase.table("config_projetos").select("projeto_id").eq("usuario_id", ID_USUARIO_LOGADO).execute()
projs = [r['projeto_id'] for r in projs_req.data]

if 'projeto_ativo' not in st.session_state:
    st.session_state.projeto_ativo = None
if 'escolha' not in st.session_state:
    st.session_state.escolha = "🏠 Dashboard" if st.session_state.projeto_ativo else "⚙️ Gestão"

s_db = 0.0
d_ini_db = None 
d_fim_db = None 

if st.session_state.projeto_ativo:
    cfg_req = supabase.table("config_projetos").select("*").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", ID_USUARIO_LOGADO).execute()
    if cfg_req.data:
        cfg = cfg_req.data[0]
        s_db = cfg.get('saldo_inicial', 0.0)
        d_ini_db = datetime.strptime(cfg['data_ini'], '%Y-%m-%d').date()
        d_fim_db = datetime.strptime(cfg['data_fim'], '%Y-%m-%d').date()

# --- 6. NAVEGAÇÃO NA SIDEBAR ---
with st.sidebar:
    st.markdown('<div class="logo-sidebar">🐋 ORCAS</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="user-email">👤 {st.session_state.usuario}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="venc-text">📅 EXPIRA EM: {venc_dt_objeto.strftime("%d/%m/%Y")}</div>', unsafe_allow_html=True)
    
    if st.session_state.projeto_ativo:
        st.markdown(f'<div class="project-tag-sidebar">Plano Ativo: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    st.divider()
    
    menu_opcoes = ["🏠 Dashboard", "📑 Lançamentos", "📅 Projetar", "✅ Conciliação", "⚙️ Gestão", "📊 Admin"]
    idx_inicial = menu_opcoes.index(st.session_state.escolha) if st.session_state.escolha in menu_opcoes else 4
    
    # IMPORTANTE: No momento em que o rádio muda, setamos o estado como recolhido
    escolha_temp = st.radio("Menu de Navegação", menu_opcoes, index=idx_inicial)
    
    if escolha_temp != st.session_state.escolha:
        st.session_state.escolha = escolha_temp
        # Comando definitivo via JS Eval para clicar no botão de fechar nativo
        streamlit_js_eval(js_expressions="window.parent.document.querySelector('button[aria-label=\"Close sidebar\"]').click()")
        st.rerun()
    
    st.divider()
    if st.button("Sair do Sistema"):
        st.session_state.clear()
        st.rerun()

# --- 7. CARREGAMENTO DO DATAFRAME ---
res_l = supabase.table("lancamentos").select("*").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", ID_USUARIO_LOGADO).order("data").execute()
df = pd.DataFrame(res_l.data)

if not df.empty:
    df.columns = [c.lower() for c in df.columns]
else:
    df = pd.DataFrame(columns=['id', 'data', 'descricao', 'tipo', 'valor_plan', 'valor_real', 'status', 'projeto_id', 'usuario_id'])

# --- 8. ROTEAMENTO ---
st.markdown("<div id='topo-ancora'></div>", unsafe_allow_html=True)

if st.session_state.escolha == "🏠 Dashboard":
    dash.exibir_dashboard(df, supabase, ID_USUARIO_LOGADO, s_db)
elif st.session_state.escolha == "📑 Lançamentos":
    lanc.exibir_lancamentos(df, supabase, ID_USUARIO_LOGADO, d_ini_db, d_fim_db, s_db, format_moeda, ir_para_o_topo)
elif st.session_state.escolha == "📅 Projetar":
    proj.exibir_projetar(df, supabase, ID_USUARIO_LOGADO, d_fim_db, parse_moeda)
elif st.session_state.escolha == "✅ Conciliação":
    conc.exibir_conciliacao(df, supabase, ID_USUARIO_LOGADO, format_moeda, parse_moeda)
elif st.session_state.escolha == "⚙️ Gestão":
    gestao.exibir_gestao(supabase, ID_USUARIO_LOGADO, projs, d_ini_db, d_fim_db, s_db, format_moeda, parse_moeda, security)
elif st.session_state.escolha == "📊 Admin":
    adm.exibir_admin(df, supabase, ir_para_o_topo)

st.divider()
st.caption(f"ORCAS v01 | Usuário: {st.session_state.usuario} | Projeto: {st.session_state.projeto_ativo}")