import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import hashlib
import plotly.graph_objects as go
import streamlit.components.v1 as components
from supabase import Client
import random
import smtplib  # Adicione este
from email.mime.text import MIMEText # Adicione este
import os

# --- 1. IMPORTAÇÃO DOS MÓDULOS EXTERNOS ---
import orcas_v01_gestao as gestao
import orcas_v01_dashboard as dash
import orcas_v01_lancamentos as lanc
import orcas_v01_projetar as proj
import orcas_v01_conciliacao as conc
import orcas_v01_admin as adm
import orcas_v01_pagamentos as pag

# --- FUNÇÃO DE ENVIO INTEGRADA (Versão Corrigida para Porta 587/TLS) ---
def disparar_email_codigo(destinatario, codigo):
    try:
        # Puxa dos Secrets do Streamlit
        server_host = st.secrets["SMTP_SERVER"]
        server_port = int(st.secrets["SMTP_PORT"])
        user_email = st.secrets["SMTP_USER"]
        pass_email = st.secrets["SMTP_PASS"]
        
        msg = MIMEText(f"Seu código de verificação ORCAS é: {codigo}. Validade: 10 minutos.")
        msg['Subject'] = f"Código de Verificação - {codigo}"
        msg['From'] = f"ORCAS App <{user_email}>"
        msg['To'] = destinatario

        # MUDANÇA AQUI: smtplib.SMTP em vez de SMTP_SSL
        server = smtplib.SMTP(server_host, server_port)
        server.starttls() # Inicia a segurança TLS necessária para a porta 587
        server.login(user_email, pass_email)
        server.sendmail(user_email, destinatario, msg.as_string())
        server.quit()
        
        return True
    except Exception as e:
        st.error(f"Erro ao disparar e-mail: {e}")
        return False

# --- 2. SEGURANÇA E CONEXÃO ---
try:
    import orcas_v01_security as security
    supabase: Client = security.supabase
except Exception as e:
    st.error(f"Erro de conexão: Verifique o arquivo security.py. {e}")
    st.stop()

# --- 3. CONFIGURAÇÃO E ESTILO ---
st.set_page_config(
    page_title="ORCAS - Gestão Financeira", 
    page_icon="🐋", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

def ir_para_o_topo():
    components.html("""<script>window.parent.document.getElementById('topo-ancora').scrollIntoView();</script>""", height=0)

# FUNÇÃO PARA RECOLHER O MENU VIA CLIQUE NO BOTÃO NATIVO
def recolher_menu_via_clique():
    components.html(
        """
        <script>
            var fechar = window.parent.document.querySelector('button[aria-label="Close sidebar"]');
            if (fechar) { fechar.click(); }
        </script>
        """,
        height=0,
    )

st.markdown("""
    <style>
    /* 1. Oculta menus nativos e footer */
    #MainMenu {visibility: hidden;} 
    footer {visibility: hidden;}
    .stAppDeployButton {display:none !important;}
    [data-testid="stStatusWidget"] {display:none !important;}
    
    /* 2. SOLUÇÃO PARA O BOTÃO >> (MENU CELULAR) */
    [data-testid="stSidebarCollapsedControl"] {
        top: 60px !important; 
        left: 20px !important;
        background-color: #1E3A8A !important; /* Azul ORCAS */
        border-radius: 10px !important;
        width: 45px !important;
        height: 45px !important;
        display: flex !important;
        z-index: 9999999 !important;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.3) !important;
    }

    /* Ícone branco no botão do celular */
    [data-testid="stSidebarCollapsedControl"] button svg {
        fill: white !important;
        width: 25px !important;
        height: 25px !important;
    }

    [data-testid="stHeader"] {
        background-color: rgba(0,0,0,0) !important;
    }

    /* 3. Remove badges flutuantes */
    [data-testid="stDecoration"],
    .viewerBadge_container__1QSob,
    .viewerBadge_link__1S137,
    div[class*="stDecoration"] {
        display: none !important;
        visibility: hidden !important;
    }

    /* 4. Ajuste de altura para conteúdo principal */
    .block-container {
        padding-top: 3.5rem !important;
        margin-top: -1.0rem !important;
    }

    /* 5. FORÇA COMPACTAÇÃO RIGOROSA DE TABELAS */
    [data-testid="stTable"] td, [data-testid="stTable"] th,
    [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th,
    table td, table th {
        white-space: nowrap !important;
        word-break: keep-all !important;
    }
    
    [data-testid="stTable"], [data-testid="stDataFrame"] {
        overflow-x: auto !important;
    }

    /* 6. ESTILOS CUSTOMIZADOS ORCAS (Restaurados) */
    .logo-sidebar { 
        font-size: 2.2rem !important; 
        font-weight: bold; 
        color: #1E3A8A; 
        font-family: 'Arial Black', sans-serif; 
        margin-bottom: 20px; 
    }
    
    .user-email { 
        font-size: 0.85rem; 
        color: #64748b; 
        margin-bottom: 2px; 
    }
    
    .venc-text { 
        font-size: 0.8rem; 
        color: #e11d48; 
        font-weight: bold; 
        margin-bottom: 10px; 
    }
    
    .titulo-tela { 
        font-size: 1.6rem; 
        font-weight: bold; 
        color: #1E3A8A; 
        border-bottom: 2px solid #E5E7EB; 
        margin-bottom: 15px; 
        padding-bottom: 5px; 
    }
    
    .project-tag-sidebar { 
        color: #1E3A8A; 
        font-weight: bold; 
        font-size: 0.9rem; 
        margin-bottom: 15px; 
        padding: 8px; 
        border-left: 5px solid #1E3A8A; 
        background: #F3F4F6; 
        border-radius: 4px; 
    }
    
    /* Garante que textos de alerta e info quebrem linha normalmente */
    .info-pagamento, .stAlert p { 
        white-space: normal !important; 
        word-wrap: break-word !important; 
        display: block !important;
    }

    /* 7. RESET ESTÉTICO DO MENU LATERAL (Para voltar ao Anexo 02) */
    /* Garante fonte padrão do Streamlit nos itens do menu */
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
        font-size: 1rem !important;
        font-weight: 500 !important;
        color: #31333F !important;
    }
    
    /* Ajuste de espaçamento entre itens do rádio */
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
        gap: 0.5rem !important;
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

# --- 4. LOGIN ---
if 'logado' not in st.session_state:
    st.session_state.logado = False
if 'etapa_auth' not in st.session_state:
    st.session_state.etapa_auth = "login"

if not st.session_state.logado:
    st.markdown("<h1 style='text-align: center; margin-top: 50px;'>🐋 ORCAS</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    
    with c2:
        if st.session_state.etapa_auth == "login":
            aba = st.tabs(["Acessar Conta", "Criar Nova Conta"])
            
            with aba[0]:
                em = st.text_input("E-mail Cadastrado")
                se = st.text_input("Senha de Acesso", type="password")
                col_b1, col_b2 = st.columns(2)
                if col_b1.button("Entrar no Sistema"):
                    senha_hash = hashlib.sha256(str.encode(se)).hexdigest()
                    res = supabase.table("usuarios").select("id, nome, email, celular, vencimento, zap_ativo").eq("email", em).eq("senha", senha_hash).execute()
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
                
                if col_b2.button("Esqueci minha Senha"):
                    st.session_state.etapa_auth = "esqueci_senha"
                    st.rerun()

            with aba[1]:
                new_nome = st.text_input("Nome Completo")
                new_email = st.text_input("E-mail")
                new_celular = st.text_input("Celular (com DDD)")
                
                col_env1, col_env2 = st.columns(2)
                
                if col_env1.button("Enviar Código para Celular"):
                    if new_email and new_celular:
                        codigo = str(random.randint(100000, 999999))
                        st.session_state.codigo_verificacao = codigo
                        st.session_state.codigo_timestamp = datetime.now()
                        st.session_state.temp_user_data = {"nome": new_nome, "email": new_email, "celular": new_celular}
                        st.info(f"Código enviado para o celular {new_celular}") 
                    else:
                        st.error("Preencha E-mail e Celular para receber o código.")
                
                if col_env2.button("Enviar Código para E-mail"):
                    if new_email:
                        codigo = str(random.randint(100000, 999999))
                        if disparar_email_codigo(new_email, codigo):
                            st.session_state.codigo_verificacao = codigo
                            st.session_state.codigo_timestamp = datetime.now()
                            st.session_state.temp_user_data = {"nome": new_nome, "email": new_email, "celular": new_celular}
                            st.info(f"Código enviado para o e-mail {new_email}")
                    else:
                        st.error("Preencha o campo E-mail para receber o código.")
                
                cod_input = st.text_input("Digite o Código recebido no Celular ou no E-mail abaixo e clique em [Validar Código]", key="new_acc_code")
                
                if st.button("Validar Código"):
                    if 'codigo_timestamp' in st.session_state:
                        decorrido = (datetime.now() - st.session_state.codigo_timestamp).total_seconds() / 60
                        if decorrido > 10:
                            st.error("O código expirou (validade de 10 minutos). Solicite um novo.")
                        elif cod_input == st.session_state.get('codigo_verificacao'):
                            st.session_state.etapa_auth = "definir_senha"
                            st.rerun()
                        else:
                            st.error("Código inválido.")
                    else:
                        st.error("Solicite um código antes de validar.")

                if st.button("Voltar", key="btn_voltar_new"):
                    st.session_state.etapa_auth = "login"
                    st.rerun()

        elif st.session_state.etapa_auth == "esqueci_senha":
            st.subheader("Verificação de Segurança")
            
            # Usando uma chave que o navegador não associa a e-mail para evitar autofill
            conta_id = st.text_input("Informe a identificação da conta", key="usr_identity_check")
            
            col_rec1, col_rec2 = st.columns(2)
            if col_rec1.button("Enviar Código para Celular"):
                if conta_id:
                    res = supabase.table("usuarios").select("celular").eq("email", conta_id).execute()
                    if res.data:
                        codigo = str(random.randint(100000, 999999))
                        st.session_state.codigo_verificacao = codigo
                        st.session_state.codigo_timestamp = datetime.now()
                        st.session_state.temp_email = conta_id
                        st.info(f"Código enviado para o celular cadastrado.")
                    else:
                        st.error("Conta não localizada.")
                else:
                    st.warning("Informe o e-mail primeiro.")

            if col_rec2.button("Enviar Código para E-mail"):
                if conta_id:
                    res = supabase.table("usuarios").select("email").eq("email", conta_id).execute()
                    if res.data:
                        codigo = str(random.randint(100000, 999999))
                        if disparar_email_codigo(conta_id, codigo):
                            st.session_state.codigo_verificacao = codigo
                            st.session_state.codigo_timestamp = datetime.now()
                            st.session_state.temp_email = conta_id
                            st.info(f"Código enviado para o e-mail cadastrado.")
                    else:
                        st.error("Conta não localizada.")
                else:
                    st.warning("Informe o e-mail primeiro.")

            st.write("---")
            
            # Campo de código com nome e placeholder que 'quebram' o preenchimento automático do navegador
            input_val = st.text_input(
                "Digite a sequência numérica recebida", 
                value="", 
                placeholder="Ex: 123456",
                key="field_code_validation_secure"
            )

            if st.button("Validar Código", use_container_width=True):
                if 'codigo_timestamp' in st.session_state:
                    decorrido = (datetime.now() - st.session_state.codigo_timestamp).total_seconds() / 60
                    if decorrido > 10:
                        st.error("O código expirou. Solicite um novo.")
                    elif input_val == st.session_state.get('codigo_verificacao'):
                        # Se validou, garante que o e-mail alvo vá para a próxima etapa
                        st.session_state.temp_email = conta_id
                        st.session_state.etapa_auth = "definir_senha"
                        st.rerun()
                    else:
                        st.error("Sequência numérica incorreta.")
                else:
                    st.error("Gere um código antes de validar.")
            
            if st.button("Voltar", key="btn_voltar_forgot_final"):
                st.session_state.etapa_auth = "login"
                st.rerun()

        elif st.session_state.etapa_auth == "definir_senha":
            st.subheader("Definir Nova Senha")
            nova_se = st.text_input("Nova Senha", type="password")
            conf_se = st.text_input("Confirme a Nova Senha", type="password")
            
            if st.button("Finalizar e Entrar"):
                if nova_se == conf_se and len(nova_se) > 0:
                    senha_hash = hashlib.sha256(str.encode(nova_se)).hexdigest()
                    
                    if "temp_user_data" in st.session_state:
                        d = st.session_state.temp_user_data
                        venc_inicial = (datetime.now() + timedelta(days=7)).date().strftime('%Y-%m-%d')
                        res = supabase.table("usuarios").insert({
                            "nome": d['nome'], "email": d['email'], "celular": d['celular'], 
                            "senha": senha_hash, "vencimento": venc_inicial
                        }).execute()
                        user_id = res.data[0]['id']
                        user_email = d['email']
                        user_venc = venc_inicial
                    else:
                        user_email = st.session_state.temp_email
                        res = supabase.table("usuarios").update({"senha": senha_hash}).eq("email", user_email).execute()
                        user_id = res.data[0]['id']
                        user_venc = res.data[0]['vencimento']

                    st.session_state.logado = True
                    st.session_state.CHAVE_MESTRA_UUID = str(user_id)
                    st.session_state.usuario = user_email
                    st.session_state.vencimento = str(user_venc)
                    st.session_state.projeto_ativo = None
                    st.rerun()
                else:
                    st.error("As senhas não coincidem ou estão vazias.")
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

s_db, d_ini_db, d_fim_db = 0.0, None, None
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
    # menu_opcoes = ["🏠 Dashboard", "📑 Lançamentos", "📅 Projetar", "✅ Conciliação", "⚙️ Gestão", "📊 Admin"]
    # Incluido em 2026-04-25 "💳 Pagamentos"
    opcoes_menu = ["🏠 Dashboard", "📝 Lançamentos", "🗓️ Projetar", "✅ Conciliação", "⚙️ Gestão", "📊 Admin", "💳 Pagamentos"]

    idx_inicial = menu_opcoes.index(st.session_state.escolha) if st.session_state.escolha in menu_opcoes else 4
    
    escolha_temp = st.radio("Menu de Navegação", menu_opcoes, index=idx_inicial)
    
    if escolha_temp != st.session_state.escolha:
        st.session_state.escolha = escolha_temp
        recolher_menu_via_clique() 
        st.rerun()
    
    st.divider()
    if st.button("Sair do Sistema"):
        st.session_state.clear()
        st.rerun()

# --- 7. CARREGAMENTO DOS DADOS ---
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
    adm.exibir_admin(df, supabase, ID_USUARIO_LOGADO, ir_para_o_topo)

# ... (Bloco de roteamento inserido -PAGAMENTOS- em 2026-04-24)

elif st.session_state.escolha == "💳 Pagamentos":
    pag.exibir_pagamentos(supabase, ID_USUARIO_LOGADO)

# --- O RODAPÉ DEVE VIR ANTES DO STOP ---
st.divider()
st.caption(f"ORCAS v01 | Usuário: {st.session_state.usuario} | Projeto: {st.session_state.projeto_ativo}")

# --- O STOP VEM POR ÚLTIMO ---
st.stop()