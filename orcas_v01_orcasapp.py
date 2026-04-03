import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import hashlib
import plotly.graph_objects as go
import streamlit.components.v1 as components
from supabase import Client

# --- IMPORTAÇÃO DOS MÓDULOS EXTERNOS (Adequação para Modularização) ---
import orcas_v01_gestao as gestao
import orcas_v01_dashboard as dash
import orcas_v01_lancamentos as lanc
import orcas_v01_projetar as proj
import orcas_v01_conciliacao as conc
import orcas_v01_admin as adm

# --- 1. SEGURANÇA E CONEXÃO ---
try:
    import orcas_v01_security as security
    supabase: Client = security.supabase
except Exception as e:
    st.error(f"Erro de conexão: Verifique o arquivo security.py e sua conexão. {e}")
    st.stop()

# --- 2. CONFIGURAÇÃO E ESTILO ---
st.set_page_config(
    page_title="ORCAS - Gestão Financeira", 
    page_icon="🐋", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

def ir_para_o_topo():
    components.html("""<script>window.parent.document.getElementById('topo-ancora').scrollIntoView();</script>""", height=0)

st.markdown("""
    <style>
    /* Oculta elementos nativos do Streamlit */
    #MainMenu {visibility: hidden; display: none;} 
    footer {visibility: hidden; display: none;}
    header {visibility: hidden; display: none;}
    .stAppDeployButton {display:none;}
    [data-testid="stStatusWidget"] {display:none;}
    [data-testid="stHeader"] {display: none;}
    [data-testid="stToolbar"] {display: none;}
    .stAppToolbar {display: none;}
    [data-testid="stDecoration"] {display: none;}

    /* HEADER FIXO NO TOPO */
    .fixed-header {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        background-color: white;
        z-index: 999;
        border-bottom: 2px solid #E5E7EB;
        padding: 10px 20px;
    }

    /* Ajuste para o conteúdo não ficar embaixo do header fixo */
    .block-container { 
        padding-top: 120px !important; 
    }
    
    /* Estilos personalizados do ORCAS */
    .logo-header { font-size: 1.8rem !important; font-weight: bold; color: #1E3A8A; font-family: 'Arial Black', sans-serif; display: inline-block; }
    .info-header { font-size: 0.75rem; color: #64748b; line-height: 1.2; }
    .venc-header { font-size: 0.75rem; color: #e11d48; font-weight: bold; }
    .titulo-tela { font-size: 1.6rem; font-weight: bold; color: #1E3A8A; border-bottom: 2px solid #E5E7EB; margin-bottom: 15px; padding-bottom: 5px; }
    
    /* Ajuste para o texto de assinatura na Gestão ser exibido completo */
    .stAlert p { white-space: pre-wrap !important; }
    
    /* Botões de navegação em linha */
    div.stButton > button {
        border-radius: 5px;
        padding: 5px 10px;
        font-size: 14px;
    }
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

# --- 3. LOGIN ---
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
                    st.session_state.escolha = "⚙️ Gestão"
                    st.rerun()
                else:
                    st.error("E-mail ou senha incorretos.")
            
            if col_btn_l2.button("Esqueci minha Senha"):
                st.info("Por favor, entre em contato com o suporte administrativo do ORCAS.")

        with aba[1]:
            st.info("Para criar uma nova conta, entre em contato com o suporte administrativo do ORCAS.")
    st.stop()

# --- 4. ESTADO E DADOS ---
ID_USUARIO_LOGADO = str(st.session_state.get('CHAVE_MESTRA_UUID', ''))
vencimento_str = st.session_state.get('vencimento', '2026-01-01')
venc_dt_objeto = datetime.strptime(vencimento_str, '%Y-%m-%d').date()

if ID_USUARIO_LOGADO:
    security.verificar_bloqueio_v01(ID_USUARIO_LOGADO, (venc_dt_objeto - datetime.now().date()).days)

projs_req = supabase.table("config_projetos").select("projeto_id").eq("usuario_id", ID_USUARIO_LOGADO).execute()
projs = [r['projeto_id'] for r in projs_req.data]

if 'projeto_ativo' not in st.session_state:
    st.session_state.projeto_ativo = None
if 'msg_sucesso' not in st.session_state:
    st.session_state.msg_sucesso = None
if 'confirmar_exclusao_ativa' not in st.session_state:
    st.session_state.confirmar_exclusao_ativa = False
if 'escolha' not in st.session_state:
    st.session_state.escolha = "⚙️ Gestão" if st.session_state.projeto_ativo is None else "🏠 Dashboard"

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

# --- 5. HEADER FIXO E NAVEGAÇÃO ---
# Container fixo simulado via columns no topo (dentro do fluxo de renderização do Streamlit com ancoragem CSS)
st.markdown("<div id='topo-ancora'></div>", unsafe_allow_html=True)

with st.container():
    # Primeira linha: Logo e Info do Usuário
    c_l, c_i, c_p, c_s = st.columns([1.5, 2, 2, 1])
    with c_l:
        st.markdown('<div class="logo-header">🐋 ORCAS</div>', unsafe_allow_html=True)
    with c_i:
        st.markdown(f'<div class="info-header">👤 {st.session_state.usuario}<br><span class="venc-header">📅 EXPIRA EM: {venc_dt_objeto.strftime("%d/%m/%Y")}</span></div>', unsafe_allow_html=True)
    with c_p:
        if st.session_state.projeto_ativo:
            st.markdown(f'<div style="color:#1E3A8A; font-weight:bold; font-size:0.9rem; margin-top:5px;">Plano: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    with c_s:
        if st.button("Sair"):
            st.session_state.clear()
            st.rerun()

    # Segunda linha: Botões de Navegação (Solução para o bug do Combobox)
    menu_opcoes = ["🏠 Dashboard", "📑 Lançamentos", "📅 Projetar", "✅ Conciliação", "⚙️ Gestão", "📊 Admin"]
    cols_nav = st.columns(len(menu_opcoes))
    
    for i, opt in enumerate(menu_opcoes):
        # Destaca o botão da tela ativa
        tipo_btn = "primary" if st.session_state.escolha == opt else "secondary"
        if cols_nav[i].button(opt, key=f"btn_nav_{i}", type=tipo_btn, use_container_width=True):
            st.session_state.escolha = opt
            st.rerun()

st.divider()

escolha = st.session_state.escolha

if st.session_state.projeto_ativo is None and escolha not in ["⚙️ Gestão", "📊 Admin"]:
    st.session_state.escolha = "⚙️ Gestão"
    st.rerun()

# --- 6. CARREGAMENTO DO DATAFRAME ---
res_l = supabase.table("lancamentos").select("*").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", ID_USUARIO_LOGADO).order("data").execute()
df = pd.DataFrame(res_l.data)

if not df.empty:
    df.columns = [c.lower() for c in df.columns]
else:
    df = pd.DataFrame(columns=[
        'id', 'data', 'descricao', 'tipo', 'valor_plan', 'valor_real', 
        'status', 'permite_parcial', 'projeto_id', 'usuario_id', 
        'data_vencimento', 'id_pai', 'usar_media', 'complemento_texto',
        'correcao_freq', 'correcao_valor', 'parcial_real'
    ])

# --- 7. ROTEAMENTO DAS TELAS ---
if escolha == "🏠 Dashboard":
    dash.exibir_dashboard(df, supabase, ID_USUARIO_LOGADO, s_db)

elif escolha == "📑 Lançamentos":
    lanc.exibir_lancamentos(df, supabase, ID_USUARIO_LOGADO, d_ini_db, d_fim_db, s_db, format_moeda, ir_para_o_topo)

elif escolha == "📅 Projetar":
    proj.exibir_projetar(df, supabase, ID_USUARIO_LOGADO, d_fim_db, parse_moeda)

elif escolha == "✅ Conciliação":
    conc.exibir_conciliacao(df, supabase, ID_USUARIO_LOGADO, format_moeda, parse_moeda)

elif escolha == "⚙️ Gestão":
    gestao.exibir_gestao(supabase, ID_USUARIO_LOGADO, projs, d_ini_db, d_fim_db, s_db, format_moeda, parse_moeda, security)

elif escolha == "📊 Admin":
    adm.exibir_admin(df, supabase, ir_para_o_topo)

# --- RODAPÉ ---
st.divider()
st.caption(f"ORCAS v01 | Usuário: {st.session_state.usuario} | Projeto: {st.session_state.projeto_ativo}")