import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import hashlib
import plotly.graph_objects as go
import streamlit.components.v1 as components

# Importação ativada para o funcionamento do retorno automático
import orcas_v01_retornodomp as retornodomp

# from supabase import Client

from supabase import create_client, Client

import random
import smtplib  # Adicione este
from email.mime.text import MIMEText # Adicione este
import os

# --- 1. IMPORTAÇÃO DOS MÓDULOS EXTERNOS ---
#  import orcas_v01_gestao as gestao  - Está sendo importado depois do LOGIN
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

# --- 2. SEGURANÇA E CONEXÃO (Definição do objeto supabase) ---
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

# ==============================================================================
# INÍCIO INSERÇÃO: INTERCEPTAÇÃO INTELIGENTE DE RETORNO DO MERCADO PAGO E LOGIN AUTOMÁTICO
# ==============================================================================
import streamlit.components.v1 as components
import zoneinfo
from datetime import datetime, timedelta

status_retorno = None
pref_id = None

if 'logado' not in st.session_state:
    st.session_state.logado = False

query_params = st.query_params

# --- ESTRATÉGIA 1: INTEGRAÇÃO COM PARAMETROS DE BYPASS NA URL ---
if "bypass_uid" in query_params and "bypass_val" in query_params:
    uid_retorno = str(query_params["bypass_uid"]).strip()
    valor_retorno = float(query_params["bypass_val"])
    plano_retorno = query_params.get("bypass_plano", "")
    venc_retorno_str = query_params.get("bypass_venc", "")

    try:
        # Busca o registro temporário para não perder as definições da tela
        req_temp = supabase.table("pagamentos_temp").select("*").eq("usuario_id", uid_retorno).execute()
        
        if req_temp.data:
            dados_temp = req_temp.data[0]
            fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
            hoje_br_string = datetime.now(fuso_br).strftime('%Y-%m-%d')
            
            v_tipo_renovacao = dados_temp.get("tipo_renovacao")
            
            if not venc_retorno_str:
                venc_retorno_str = (datetime.now(fuso_br).date() + timedelta(days=30)).strftime('%Y-%m-%d')
            
            # Atualiza o usuário contendo explicitamente o tipo_renovacao que estava faltando
            try:
                supabase.table("usuarios").update({
                    "data_ult_assinat": hoje_br_string,
                    "valor_pago": valor_retorno,
                    "vencimento": venc_retorno_str,
                    "tipo_renovacao": v_tipo_renovacao  # Grava o plano escolhido na tela (ex: 48 meses)
                }).eq("id", uid_retorno).execute()
            except Exception as erro_banco:
                st.error(f"Erro ao consolidar dados cadastrais da assinatura: {erro_banco}")

            # Atualiza a tabela config_projetos com os estados de zap e email correspondentes
            v_projeto_id = plano_retorno if plano_retorno else dados_temp.get('projeto_id')
            if v_projeto_id:
                try:
                    supabase.table("config_projetos").update({
                        "data_ini": dados_temp.get("data_ini"),
                        "data_fim": dados_temp.get("data_fim"),
                        "zap_ativo": dados_temp.get("zap_ativo"),
                        "email_ativo": dados_temp.get("email_ativo")
                    }).eq("projeto_id", v_projeto_id).eq("usuario_id", uid_retorno).execute()
                except Exception:
                    pass

            # Montagem das variáveis de sessão baseadas no banco
            req_user = supabase.table("usuarios").select("*").eq("id", uid_retorno).execute()
            if req_user.data:
                u_dados = req_user.data[0]
                
                st.session_state.logado = True
                st.session_state.CHAVE_MESTRA_UUID = str(uid_retorno)
                st.session_state.usuario = u_dados.get('email', 'Usuário Confirmado')
                st.session_state.usuario_email = u_dados.get('email', '')
                st.session_state.vencimento = venc_retorno_str
                st.session_state.projeto_ativo = v_projeto_id
                st.session_state.zap_ativo = dados_temp.get("zap_ativo", False)
                st.session_state.email_ativo = dados_temp.get("email_ativo", 1)
                st.session_state.escolha = "⚙️ Gestão"
                
                # 🔥 DELEÇÃO LIMPA: Remove o registro temporário consumido para liberar espaço
                try:
                    supabase.table("pagamentos_temp").delete().eq("usuario_id", uid_retorno).execute()
                except Exception:
                    pass
                
                components.html("""
                    <script>
                        localStorage.setItem('orcas_payment_success', 'true');
                        if (window.opener) {
                            window.close();
                        }
                    </script>
                """, height=0)
                
                st.query_params.clear()
                st.rerun()
        else:
            st.warning("⚠️ Nota: O registro temporário de pagamento já foi processado ou expirou.")
            st.query_params.clear()
            
    except Exception as erro_bypass:
        st.error(f"Erro interno ao processar validação automática: {erro_bypass}")

# --- ESTRATÉGIA 2: MODELO DE RETORNO CLÁSSICO COM PARAMETROS MP ---
elif query_params and len(query_params) > 0:
    status_retorno = query_params.get("status") or query_params.get("collection_status")
    pref_id = query_params.get("preference_id") or query_params.get("collection_id")

if status_retorno and pref_id and not st.session_state.logado:
    if status_retorno in ["approved", "authorized", "pending"]:
        with st.spinner("🚀 Processando seu pagamento e aplicando as alterações do seu plano..."):
            usuario_auto = retornodomp.tratar_retorno(supabase, pref_id, status_retorno)
            if usuario_auto and isinstance(usuario_auto, dict):
                st.session_state.logado = True
                st.session_state.CHERA_MESTRA_UUID = str(usuario_auto.get('id', ''))
                st.session_state.CHAVE_MESTRA_UUID = str(usuario_auto.get('id', ''))
                st.session_state.usuario = usuario_auto.get('email', '')
                st.session_state.usuario_email = usuario_auto.get('email', '')
                st.session_state.vencimento = str(usuario_auto.get('vencimento', ''))
                st.session_state.projeto_ativo = usuario_auto.get("projeto_ativo")
                st.session_state.zap_ativo = usuario_auto.get('zap_ativo', False)
                st.session_state.email_ativo = usuario_auto.get('email_ativo', 1)
                st.session_state.pagamento_realizado_sucesso = True
                st.query_params.clear()
                st.session_state.escolha = "⚙️ Gestão"
                st.rerun()

if not st.session_state.get('CHAVE_MESTRA_UUID'):
    st.session_state['CHAVE_MESTRA_UUID'] = ''
# ==============================================================================
# FIM INSERÇÃO
# ==============================================================================

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
                            # --- CÓDIGO PROVISÓRIO DE TESTE (Criação de Conta - E-mail) ---
                            st.success(f"⚙️ [TESTE CRIAR CONTA - Especially for my son Diego] Código: **{codigo}**")   
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
                        
                        # --- ADEQUAÇÃO DO ITEM (3): GERAÇÃO EXATA DOS 7 DIAS DE DEGUSTAÇÃO ---
                        venc_inicial = (datetime.now() + timedelta(days=7)).date().strftime('%Y-%m-%d')
                        
                        res = supabase.table("usuarios").insert({
                            "nome": d['nome'], 
                            "email": d['email'], 
                            "celular": d['celular'], 
                            "senha": senha_hash, 
                            "vencimento": venc_inicial
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

if not st.session_state.get("logado"):
    st.warning("⚠️ Sessão encerrada ou inválida. Por favor, faça login para acessar o sistema.")
    st.stop()

# Captura de chaves e variáveis com valores padrão seguros para evitar quebras de escopo
ID_USUARIO_LOGADO = str(st.session_state.get('CHAVE_MESTRA_UUID', ''))
vencimento_str = st.session_state.get('vencimento', '')

# Tratamento ultra-seguro para a string de vencimento do banco de dados
if not vencimento_str or vencimento_str.strip() == "":
    venc_dt_objeto = datetime.now().date()
else:
    try:
        venc_dt_objeto = datetime.strptime(vencimento_str, '%Y-%m-%d').date()
    except Exception:
        venc_dt_objeto = datetime.now().date()

# Executa rotina de segurança se houver usuário válido na sessão
if ID_USUARIO_LOGADO:
    try:
        security.verificar_bloqueio_v01(ID_USUARIO_LOGADO, (venc_dt_objeto - datetime.now().date()).days)
    except Exception:
        pass

# Busca os projetos associados à conta do usuário logado
try:
    projs_req = supabase.table("config_projetos").select("projeto_id").eq("usuario_id", ID_USUARIO_LOGADO).execute()
    projs = [r['projeto_id'] for r in projs_req.data] if projs_req.data else []
except Exception:
    projs = []

# Inicializa as chaves essenciais de navegação caso não existam
if 'projeto_ativo' not in st.session_state:
    st.session_state.projeto_ativo = None

if 'escolha' not in st.session_state:
    st.session_state.escolha = "🏠 Dashboard" if st.session_state.projeto_ativo else "⚙️ Gestão"

# Recuperação dos parâmetros de saldo e período do plano carregado
s_db, d_ini_db, d_fim_db = 0.0, None, None
if st.session_state.projeto_ativo and ID_USUARIO_LOGADO:
    try:
        cfg_req = supabase.table("config_projetos").select("*").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", ID_USUARIO_LOGADO).execute()
        if cfg_req.data:
            cfg = cfg_req.data[0]
            s_db = cfg.get('saldo_inicial', 0.0)
            if cfg.get('data_ini'):
                d_ini_db = datetime.strptime(cfg['data_ini'], '%Y-%m-%d').date()
            if cfg.get('data_fim'):
                d_fim_db = datetime.strptime(cfg['data_fim'], '%Y-%m-%d').date()
    except Exception:
        pass

# --- 6. NAVEGAÇÃO NA SIDEBAR ---
with st.sidebar:
    st.markdown('<div class="logo-sidebar">🐋 ORCAS</div>', unsafe_allow_html=True)
    
    usuario_exibir = st.session_state.get('usuario', 'Usuário Logado')
    st.markdown(f'<div class="user-email">👤 {usuario_exibir}</div>', unsafe_allow_html=True)
    
    # --- LÓGICA DE AVISO DE VENCIMENTO COMERCIAL ---
    hoje_atual = datetime.now().date()
    dias_para_vencer = (venc_dt_objeto - hoje_atual).days
    
    if dias_para_vencer < 0:
        texto_venc = f"⚠️ EXPIRADO EM: {venc_dt_objeto.strftime('%d/%m/%Y')}"
        cor_venc = "#FF0000"  # Vermelho
        bloqueado = True
    elif dias_para_vencer <= 3:
        texto_venc = f"⏳ EXPIRA EM: {venc_dt_objeto.strftime('%d/%m/%Y')} ({dias_para_vencer}d)"
        cor_venc = "#FFA500"  # Laranja
        bloqueado = False
    else:
        texto_venc = f"📅 EXPIRA EM: {venc_dt_objeto.strftime('%d/%m/%Y')}"
        cor_venc = "#333333"  # Cor padrão padronizada
        bloqueado = False

    st.markdown(f'<div style="color:{cor_venc}; font-weight:bold; font-size:13px; padding:5px 0;">{texto_venc}</div>', unsafe_allow_html=True)
    
    if st.session_state.projeto_ativo:
        st.markdown(f'<div class="project-tag-sidebar">Plano Ativo: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # Restrição de menu baseada no status financeiro da assinatura
    if bloqueado:
        menu_opcoes = ["⚙️ Gestão"]
        st.session_state.escolha = "⚙️ Gestão"
        st.warning("Assinatura Expirada! Acesse a Gestão para renovar.")
    else:
        menu_opcoes = ["🏠 Dashboard", "📝 Lançamentos", "🗓️ Projetar", "✅ Conciliação", "⚙️ Gestão", "📊 Admin"]

    # Posicionamento do marcador de seleção da barra lateral
    if st.session_state.escolha in menu_opcoes:
        idx_selecionado = menu_opcoes.index(st.session_state.escolha)
    else:
        idx_selecionado = menu_opcoes.index("⚙️ Gestão") 

    # Renderização e captura da escolha do rádio
    escolha_sidebar = st.radio("Menu de Navegação", menu_opcoes, index=idx_selecionado)

    # Disparador de mudança de rota se houver clique do usuário
    if escolha_sidebar != st.session_state.escolha:
        if st.session_state.escolha == "💳 Pagamentos" and escolha_sidebar == "⚙️ Gestão":
            pass 
        else:
            st.session_state.escolha = escolha_sidebar
            st.rerun()

    st.divider()
    if st.button("Sair do Sistema"):
        st.session_state.clear()
        st.rerun()

# --- 7. CARREGAMENTO DOS DADOS ---
try:
    res_l = supabase.table("lancamentos").select("*").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", ID_USUARIO_LOGADO).order("data").execute()
    df = pd.DataFrame(res_l.data)
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
    else:
        df = pd.DataFrame(columns=['id', 'data', 'descricao', 'tipo', 'valor_plan', 'valor_real', 'status', 'projeto_id', 'usuario_id'])
except Exception:
    df = pd.DataFrame(columns=['id', 'data', 'descricao', 'tipo', 'valor_plan', 'valor_real', 'status', 'projeto_id', 'usuario_id'])

# --- 8. ROTEAMENTO ---
st.markdown("<div id='topo-ancora'></div>", unsafe_allow_html=True)

# Centralização das chamadas das sub-telas de negócio
if st.session_state.escolha == "🏠 Dashboard" and not bloqueado:
    dash.exibir_dashboard(df, supabase, ID_USUARIO_LOGADO, s_db)
elif st.session_state.escolha == "📝 Lançamentos" and not bloqueado:
    lanc.exibir_lancamentos(df, supabase, ID_USUARIO_LOGADO, d_ini_db, d_fim_db, s_db, format_moeda, ir_para_o_topo)
elif st.session_state.escolha == "🗓️ Projetar" and not bloqueado:
    proj.exibir_projetar(df, supabase, ID_USUARIO_LOGADO, d_fim_db, parse_moeda)
elif st.session_state.escolha == "✅ Conciliação" and not bloqueado:
    conc.exibir_conciliacao(df, supabase, ID_USUARIO_LOGADO, format_moeda, parse_moeda)
elif st.session_state.escolha == "⚙️ Gestão":
    import orcas_v01_gestao as gestao
    gestao.exibir_gestao(supabase, ID_USUARIO_LOGADO, projs, d_ini_db, d_fim_db, s_db, format_moeda, parse_moeda, security)
elif st.session_state.escolha == "📊 Admin" and not bloqueado:
    adm.exibir_admin(df, supabase, ID_USUARIO_LOGADO, ir_para_o_topo)
elif st.session_state.escolha == "💳 Pagamentos":
    import orcas_v01_pagamentos as pag
    pag.exibir_pagamentos(supabase, ID_USUARIO_LOGADO)
else:
    import orcas_v01_gestao as gestao
    gestao.exibir_gestao(supabase, ID_USUARIO_LOGADO, projs, d_ini_db, d_fim_db, s_db, format_moeda, parse_moeda, security)

# --- O RODAPÉ DEVE VER ANTES DO STOP ---
st.divider()
usuario_rodape = st.session_state.get('usuario', '')
st.caption(f"ORCAS v01 | Usuário: {usuario_rodape} | Projeto: {st.session_state.projeto_ativo}")

# --- O STOP VEM POR ÚLTIMO ---
st.stop()