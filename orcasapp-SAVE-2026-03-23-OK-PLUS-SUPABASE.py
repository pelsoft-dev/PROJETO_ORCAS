import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import hashlib
import plotly.graph_objects as go
import streamlit.components.v1 as components
from supabase import Client

# --- 1. SEGURANÇA E CONEXÃO ---
try:
    import orcas_v01_security as security
    supabase: Client = security.supabase
except Exception as e:
    st.error(f"Erro de conexão: Verifique o arquivo security.py e sua conexão. {e}")
    st.stop()

# --- 2. CONFIGURAÇÃO E ESTILO ---
st.set_page_config(page_title="ORCAS - Gestão Financeira", layout="wide", initial_sidebar_state="expanded")

def ir_para_o_topo():
    components.html("""<script>window.parent.document.getElementById('topo-ancora').scrollIntoView();</script>""", height=0)

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    [data-testid="stHeader"] {background: rgba(0,0,0,0) !important; color: transparent !important;}
    .block-container { padding-top: 0.1rem !important; }
    .logo-sidebar { font-size: 2.2rem !important; font-weight: bold; color: #1E3A8A; font-family: 'Arial Black', sans-serif; }
    .user-email { font-size: 0.85rem; color: #64748b; margin-bottom: 2px; }
    .venc-text { font-size: 0.8rem; color: #e11d48; font-weight: bold; margin-bottom: 10px; }
    .titulo-tela { font-size: 1.6rem; font-weight: bold; color: #1E3A8A; border-bottom: 2px solid #E5E7EB; margin-bottom: 15px; padding-bottom: 5px; }
    .project-tag-sidebar { color: #1E3A8A; font-weight: bold; font-size: 0.9rem; margin-bottom: 15px; padding: 8px; border-left: 5px solid #1E3A8A; background: #F3F4F6; border-radius: 4px; }
    div[data-testid="column"] button { width: 100% !important; }
    .info-pagamento { background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; margin-top: 10px; margin-bottom: 10px; }
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
            
            # ITEM (1): Adicionado botão Esqueci minha Senha
            col_btn_l1, col_btn_l2 = st.columns(2)
            if col_btn_l1.button("Entrar no Sistema"):
                senha_hash = hashlib.sha256(str.encode(se)).hexdigest()
                res = supabase.table("usuarios").select("id, vencimento, zap_ativo").eq("email", em).eq("senha", senha_hash).execute()
                if res.data: 
                    user_data = res.data[0]
                    st.session_state.logado = True
                    st.session_state.user_id = user_data['id']
                    st.session_state.usuario = em
                    st.session_state.vencimento = str(user_data['vencimento'])
                    st.session_state.zap_ativo = user_data.get('zap_ativo', 0)
                    st.session_state.projeto_ativo = None
                    st.rerun()
                else:
                    st.error("E-mail ou senha incorretos.")
            
            if col_btn_l2.button("Esqueci minha Senha"):
                st.info("Por favor, entre em contato com o administrador para recuperar seu acesso.")

        with aba[1]:
            st.info("Para criar uma nova conta, entre em contato com o suporte administrativo do ORCAS.")
    st.stop()

# --- 4. ESTADO E DADOS ---
uid = st.session_state.user_id
venc_dt = datetime.strptime(st.session_state.vencimento, '%Y-%m-%d').date()
dias_rest = (venc_dt - datetime.now().date()).days
security.verificar_bloqueio_v01(uid, dias_rest)

projs_req = supabase.table("config_projetos").select("projeto_id").eq("usuario_id", uid).execute()
projs = [r['projeto_id'] for r in projs_req.data]

if 'projeto_ativo' not in st.session_state:
    st.session_state.projeto_ativo = None
if 'msg_sucesso' not in st.session_state:
    st.session_state.msg_sucesso = None
if 'confirmar_exclusao_ativa' not in st.session_state:
    st.session_state.confirmar_exclusao_ativa = False

s_db = 0.0
d_ini_db = datetime.now().date()
d_fim_db = (datetime.now() + timedelta(days=730)).date()

if st.session_state.projeto_ativo:
    cfg_req = supabase.table("config_projetos").select("*").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).execute()
    if cfg_req.data:
        cfg = cfg_req.data[0]
        s_db = cfg.get('saldo_inicial', 0.0)
        d_ini_db = datetime.strptime(cfg['data_ini'], '%Y-%m-%d').date()
        d_fim_db = datetime.strptime(cfg['data_fim'], '%Y-%m-%d').date()

# --- 5. BARRA LATERAL ---
with st.sidebar:
    st.markdown('<div class="logo-sidebar">🐋 ORCAS</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="user-email">👤 {st.session_state.usuario}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="venc-text">⏳ {max(0, dias_rest)} DIAS RESTANTES</div>', unsafe_allow_html=True)
    
    if st.session_state.projeto_ativo:
        st.markdown(f'<div class="project-tag-sidebar">Plano Ativo: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
        n_saldo_txt = st.text_input("Saldo Inicial", value=format_moeda(s_db))
        n_saldo_val = parse_moeda(n_saldo_txt)
        if n_saldo_val != s_db:
            dados_upsert = {"projeto_id": st.session_state.projeto_ativo, "usuario_id": uid, "saldo_inicial": n_saldo_val, "data_ini": d_ini_db.strftime('%Y-%m-%d'), "data_fim": d_fim_db.strftime('%Y-%m-%d')}
            check_exist = supabase.table("config_projetos").select("id").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).execute()
            if check_exist.data: dados_upsert["id"] = check_exist.data[0]["id"]
            supabase.table("config_projetos").upsert(dados_upsert).execute()
            st.rerun()

    st.divider()
    menu_opcoes = ["🏠 Dashboard", "📑 Lançamentos", "📅 Projetar", "✅ Conciliação", "⚙️ Gestão"]
    idx_default = 4 if st.session_state.projeto_ativo is None else 0
    escolha = st.radio("Navegação", menu_opcoes, index=idx_default, label_visibility="collapsed")
    st.divider()
    if st.button("Sair do Sistema"):
        st.session_state.clear()
        st.rerun()

st.markdown("<div id='topo-ancora'></div>", unsafe_allow_html=True)
if st.session_state.projeto_ativo is None:
    escolha = "⚙️ Gestão"
    # --- 6. CARREGAMENTO DO DATAFRAME ---
res_l = supabase.table("lancamentos").select("*").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).order("data").execute()
df = pd.DataFrame(res_l.data)

if not df.empty:
    df.columns = [c.lower() for c in df.columns]
else:
    df = pd.DataFrame(columns=['id', 'data', 'descricao', 'tipo', 'valor_plan', 'valor_real', 'status'])

# --- TELA: DASHBOARD ---
# --- TELA: DASHBOARD (Compatibilização de Saldo Realizado) ---
if escolha == "🏠 Dashboard":
    st.markdown(f'<div class="titulo-tela">Dashboard: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    if not df.empty and 'data' in df.columns:
        df['dt'] = pd.to_datetime(df['data'])
        
        # AJUSTE CIRÚRGICO: Se status é Realizado, pega valor_real. Senão, valor_plan.
        # Multiplica por 1 se Entrada e -1 se Saída.
        df['v'] = df.apply(
            lambda x: (x['valor_real'] if x['status'] == 'Realizado' else x['valor_plan']) * (1 if x['tipo'] == 'Entrada' else -1), 
            axis=1
        )
        
        df_diario = df.groupby('dt')['v'].sum().reset_index()
        df_diario['Saldo Acumulado'] = df_diario['v'].cumsum() + s_db
        
        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(
            x=df_diario['dt'], 
            y=df_diario['Saldo Acumulado'], 
            mode='lines', 
            name='Saldo', 
            line=dict(color='#1E3A8A', width=3), 
            fill='tozeroy', 
            fillcolor='rgba(30, 58, 138, 0.1)'
        ))
        fig_line.update_layout(title="Evolução do Saldo Projetado/Realizado", height=350, margin=dict(l=20, r=20, t=50, b=20), hovermode="x unified")
        st.plotly_chart(fig_line, use_container_width=True)
        
        # O gráfico de barras mensal já usava as colunas separadas, então ele permanece íntegro.
        st.subheader("Análise Mensal: Planejado x Realizado")
        df['MesAno'] = df['dt'].dt.strftime('%b/%y')
        res_mensal = df.groupby(['MesAno', 'tipo']).agg({'valor_plan':'sum', 'valor_real':'sum'}).reset_index()
        meses_ordem = df.sort_values('dt')['MesAno'].unique()
        fig_bar = go.Figure()
        cores_map = {'Entrada': {'p': '#A5D8FF', 'r': '#1E3A8A'}, 'Saída': {'p': '#FFA8A8', 'r': '#C53030'}}
        for tipo_mov in ['Entrada', 'Saída']:
            d_tipo = res_mensal[res_mensal['tipo'] == tipo_mov]
            if not d_tipo.empty:
                fig_bar.add_trace(go.Bar(x=d_tipo['MesAno'], y=d_tipo['valor_plan'], name=f'{tipo_mov} Plan.', marker_color=cores_map[tipo_mov]['p'], offsetgroup=tipo_mov, width=0.3))
                fig_bar.add_trace(go.Bar(x=d_tipo['MesAno'], y=d_tipo['valor_real'], name=f'{tipo_mov} Real.', marker_color=cores_map[tipo_mov]['r'], offsetgroup=tipo_mov, width=0.15))
        fig_bar.update_layout(barmode='group', xaxis={'categoryorder':'array', 'categoryarray':meses_ordem}, height=350)
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("💡 Nenhum dado encontrado.")
# --- TELA: LANÇAMENTOS ---
# --- TELA: LANÇAMENTOS (Ajuste no cálculo do Saldo) ---
elif escolha == "📑 Lançamentos":
    st.markdown(f'<div class="titulo-tela">Lançamentos: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    meses_periodo = []
    data_atual_loop = d_ini_db.replace(day=1)
    while data_atual_loop <= d_fim_db:
        meses_periodo.append(data_atual_loop.strftime('%Y-%m'))
        if data_atual_loop.month == 12: data_atual_loop = data_atual_loop.replace(year=data_atual_loop.year + 1, month=1)
        else: data_atual_loop = data_atual_loop.replace(month=data_atual_loop.month + 1)
    
    saldo_acumulado_mes = s_db
    for mes_str in meses_periodo:
        mask_mes = pd.to_datetime(df['data']).dt.strftime('%Y-%m') == mes_str
        df_mes = df[mask_mes].copy()
        
        # ALTERAÇÃO SOLICITADA: Considera Valor Realizado se Status for 'Realizado', senão Planejado
        if not df_mes.empty:
            entradas_mes = df_mes[df_mes['tipo'] == 'Entrada'].apply(
                lambda x: x['valor_real'] if x['status'] == 'Realizado' else x['valor_plan'], axis=1
            ).sum()
            
            saidas_mes = df_mes[df_mes['tipo'] == 'Saída'].apply(
                lambda x: x['valor_real'] if x['status'] == 'Realizado' else x['valor_plan'], axis=1
            ).sum()
        else:
            entradas_mes = 0.0
            saidas_mes = 0.0
            
        saldo_final_mes = saldo_acumulado_mes + entradas_mes - saidas_mes
        nome_mes_exibicao = datetime.strptime(mes_str, '%Y-%m').strftime('%m/%Y')
        
        with st.expander(f"📅 {nome_mes_exibicao} | Saldo Final: R$ {format_moeda(saldo_final_mes)}"):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Saldo Inicial", f"R$ {format_moeda(saldo_acumulado_mes)}")
            col2.metric("Entradas (+)", f"R$ {format_moeda(entradas_mes)}")
            col3.metric("Saídas (-)", f"R$ {format_moeda(saidas_mes)}")
            col4.metric("Saldo Final", f"R$ {format_moeda(saldo_final_mes)}")
            
            if not df_mes.empty:
                df_exibir = df_mes.sort_values('data').copy()
                df_exibir['Data'] = pd.to_datetime(df_exibir['data']).dt.strftime('%d/%m/%Y')
                df_exibir['E/S'] = df_exibir['tipo'].apply(lambda x: 'E' if x == 'Entrada' else 'S')
                df_exibir['V. Plan'] = df_exibir['valor_plan'].apply(format_moeda)
                df_exibir['V. Real'] = df_exibir['valor_real'].apply(format_moeda)
                df_exibir['Status'] = df_exibir['status'].apply(lambda x: 'PLAN' if x == 'Planejado' else 'REAL')
                
                st.table(df_exibir[['Data', 'descricao', 'E/S', 'V. Plan', 'V. Real', 'Status']])
            else:
                st.write("ℹ️ Nenhum lançamento.")
        saldo_acumulado_mes = saldo_final_mes
    if st.button("Voltar ao Topo", key="btn_topo_lanc"): ir_para_o_topo()
# --- TELA: PROJETAR ---
# --- TELA: PROJETAR ---
elif escolha == "📅 Projetar":
    st.markdown(f'<div class="titulo-tela">Projetar: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    if st.session_state.msg_sucesso: 
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    # LÓGICA DE EXCLUSÃO (AJUSTADA PARA CORRESPONDÊNCIA EXATA)
    if st.session_state.confirmar_exclusao_ativa:
        desc_sel = st.session_state.get('pj_d', '')
        d_esp = st.session_state.get('pj_data_especifica')
        
        if d_esp: 
            msg = f"⚠️ Excluir '{desc_sel}' do dia {d_esp.strftime('%d/%m/%Y')}?"
        else: 
            msg = f"⚠️ Excluir '{desc_sel}' no período de {st.session_state.pj_data_ini.strftime('%d/%m/%Y')} a {st.session_state.pj_data_fim.strftime('%d/%m/%Y')}?"
        
        st.warning(msg)
        cs, cn = st.columns(2)
        
        if cs.button("SIM"):
            # MUDANÇA AQUI: Trocamos .ilike() por .eq() para garantir que apague APENAS o nome exato
            query = supabase.table("lancamentos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).eq("descricao", desc_sel)
            
            if d_esp:
                res = query.eq("data", d_esp.strftime('%Y-%m-%d')).execute()
            else:
                res = query.gte("data", st.session_state.pj_data_ini.strftime('%Y-%m-%d')).lte("data", st.session_state.pj_data_fim.strftime('%Y-%m-%d')).execute()
            
            qtd = len(res.data) if res.data else 0
            st.session_state.msg_sucesso = f"Sucesso! {qtd} excluído(s)."
            st.session_state.confirmar_exclusao_ativa = False
            st.rerun()
            
        if cn.button("NÃO"): 
            st.session_state.confirmar_exclusao_ativa = False
            st.rerun()

    # INPUTS DA TELA
    desc = st.text_input("Descrição", key="pj_d")
    v_t = st.text_input("Valor", "0,00")
    tipo = st.selectbox("Tipo", ["Saída", "Entrada"])
    
    with st.expander("Recorrência", expanded=True):
        c1, c2, c3 = st.columns(3)
        d_m = c1.text_input("Dia do Mês (1-31 ou *)", "")
        d_s = c2.selectbox("Dia da Semana", ["", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"])
        d_e = c3.date_input("Dia Específico", value=None, format="DD/MM/YYYY", key="pj_data_especifica")
        fds = st.radio("FDS", ["Manter", "Antecipa", "Posterga"], horizontal=True)
        
    c_i, c_f = st.columns(2)
    i_p = c_i.date_input("Início", value=datetime.now().date(), format="DD/MM/YYYY", key="pj_data_ini")
    f_p = c_f.date_input("Até", value=d_fim_db, format="DD/MM/YYYY", key="pj_data_fim")
    
    b1, b2, _ = st.columns([1,1,2])

    # LÓGICA DE INCLUSÃO
    if b1.button("Incluir"):
        v = parse_moeda(v_t)
        curr = i_p
        lista_bulk = [] 
        d_map = {"Segunda":0,"Terça":1,"Quarta":2,"Quinta":3,"Sexta":4,"Sábado":5,"Domingo":6}
        
        while curr <= f_p:
            match = (d_e is None or curr == d_e) and \
                    (d_m == "" or d_m == "*" or str(curr.day) == d_m) and \
                    (d_s == "" or curr.weekday() == d_map[d_s])
            
            if match:
                dt_f = curr
                if d_m == "*" and dt_f.weekday() >= 5 and fds != "Manter": 
                    pass 
                else:
                    if fds != "Manter" and dt_f.weekday() >= 5: 
                        dt_f += timedelta(days=(2 if dt_f.weekday()==5 else 1) if fds=="Posterga" else -1)
                    
                    lista_bulk.append({
                        "projeto_id": st.session_state.projeto_ativo, 
                        "usuario_id": uid, 
                        "data": dt_f.strftime('%Y-%m-%d'), 
                        "data_vencimento": dt_f.strftime('%Y-%m-%d'),
                        "descricao": desc, 
                        "valor_plan": v, 
                        "valor_real": 0.0, 
                        "tipo": tipo, 
                        "status": 'Planejado'
                    })
            curr += timedelta(days=1)
        
        if lista_bulk:
            supabase.table("lancamentos").insert(lista_bulk).execute()
            st.session_state.msg_sucesso = f"Sucesso! {len(lista_bulk)} incluídos."
        st.rerun()

    if b2.button("Excluir"):
        if not desc: 
            st.error("Informe a descrição.")
        else: 
            st.session_state.confirmar_exclusao_ativa = True
            st.rerun()
# --- TELA: CONCILIAÇÃO ---
elif escolha == "✅ Conciliação":
    st.markdown(f'<div class="titulo-tela">Conciliação: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    hoje = datetime.now().date()
    df_c = df[pd.to_datetime(df['data']).dt.date <= hoje].sort_values('data', ascending=False)
    
    if df_c.empty: st.info("Nada para conciliar.")
    else:
        for _, r in df_c.iterrows():
            with st.container():
                # ITEM (4): Ajuste de nomes e coluna E/S
                c1, c2, c3, c4, c5 = st.columns([1.5, 0.5, 1, 1, 1])
                dt_f = pd.to_datetime(r['data']).strftime('%d/%m/%Y')
                es_tag = "E" if r['tipo'] == "Entrada" else "S"
                c1.write(f"**{dt_f}** - {r['descricao']}")
                c2.write(f"**{es_tag}**") # Coluna E/S
                c3.write(f"Planejado: {format_moeda(r['valor_plan'])}")
                
                if r['status'] == 'Planejado':
                    v_real_in = c4.text_input("Realizado", key=f"in_{r['id']}", placeholder="0,00")
                    if c5.button("Confirmar", key=f"bt_{r['id']}"):
                        # ITEM (4): Se vazio, usa o planejado automaticamente
                        v_conf = parse_moeda(v_real_in) if v_real_in else r['valor_plan']
                        supabase.table("lancamentos").update({"valor_real": v_conf, "status": 'Realizado'}).eq("id", r['id']).execute()
                        st.rerun()
                else:
                    # ITEM (4): Troca "Pago" por "Realizado"
                    c4.write(f"Realizado: {format_moeda(r['valor_real'])}")
                    c5.write("✅ Realizado")
            st.divider()
# --- TELA: GESTÃO ---
# --- TELA: GESTÃO ---
elif escolha == "⚙️ Gestão":
    st.markdown('<div class="titulo-tela">Gestão de Projetos e Assinatura</div>', unsafe_allow_html=True)
    
    if st.session_state.msg_sucesso:
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    # (2) Alteração: Trocar para outro Plano Financeiro
    lista_opcoes = ["-- Selecionar Plano --"] + projs
    fluxo_selecionado = st.selectbox("Trocar para outro Plano Financeiro:", lista_opcoes)
    
    if fluxo_selecionado != "-- Selecionar Plano --" and fluxo_selecionado != st.session_state.projeto_ativo:
        st.session_state.projeto_ativo = fluxo_selecionado
        st.rerun()

    st.divider()
    
    # (2) Alteração: Configuração do seu Plano Financeiro
    st.subheader("Configuração do seu Plano Financeiro")
    
    # (2) Alteração: Nome do Plano
    nome_fluxo_input = st.text_input("Nome do Plano (Ex: Pessoal, Empresa X)", 
                                    value=st.session_state.projeto_ativo if st.session_state.projeto_ativo else "")
    
    col_g1, col_g2 = st.columns(2)
    
    # (1) Formato dd/mm/aaaa e (2) Alteração de rótulos
    data_ini_gestao = col_g1.date_input("Data de Início do Plano", value=d_ini_db, format="DD/MM/YYYY")
    data_fim_gestao = col_g2.date_input("Data de Término do Plano", value=d_fim_db, format="DD/MM/YYYY")
    
    # (4) Campos ocultos até que um plano seja selecionado ou nomeado
    if st.session_state.projeto_ativo or (nome_fluxo_input and nome_fluxo_input.strip() != ""):
        ativar_zap = st.checkbox("Ativar Notificações via WhatsApp (+ R$ 10,00/mês)", 
                                 value=(st.session_state.get('zap_ativo', 0) == 1))
        
        valor_mensalidade = security.calcular_valor_v01(len(projs), 
                                                       data_ini_gestao.strftime('%Y-%m-%d'), 
                                                       data_fim_gestao.strftime('%Y-%m-%d'))
        
        if ativar_zap:
            valor_mensalidade += 10.0
            
        st.info(f"💳 Valor Estimado da Assinatura: **R$ {format_moeda(valor_mensalidade)} / mês**")
    
    col_btn1, col_btn2 = st.columns([1, 1])
    
    if col_btn1.button("Salvar Alterações / Criar Plano", use_container_width=True):
        if nome_fluxo_input:
            dados_projeto = {
                "projeto_id": nome_fluxo_input,
                "usuario_id": uid,
                "saldo_inicial": s_db,
                "data_ini": data_ini_gestao.strftime('%Y-%m-%d'),
                "data_fim": data_fim_gestao.strftime('%Y-%m-%d')
            }
            
            check_pj = supabase.table("config_projetos").select("id").eq("projeto_id", nome_fluxo_input).eq("usuario_id", uid).execute()
            if check_pj.data:
                dados_projeto["id"] = check_pj.data[0]["id"]
            
            supabase.table("config_projetos").upsert(dados_projeto).execute()
            
            # Só tenta atualizar zap se o campo foi exibido
            if st.session_state.projeto_ativo or nome_fluxo_input:
                supabase.table("usuarios").update({"zap_ativo": 1 if ativar_zap else 0}).eq("id", uid).execute()
                st.session_state.zap_ativo = 1 if ativar_zap else 0
            
            st.session_state.projeto_ativo = nome_fluxo_input
            st.session_state.msg_sucesso = "✅ Configurações salvas!"
            st.rerun()
        else:
            st.error("Por favor, insira um nome para o plano.")

    # (3) Excluir Plano Atual (Sem Zona de Perigo, com confirmação direta)
    if st.session_state.projeto_ativo:
        st.divider()
        if st.button("EXCLUIR PLANO ATUAL", type="primary", use_container_width=True):
            st.session_state.confirmar_exclusao_plano = True

        if st.session_state.get('confirmar_exclusao_plano', False):
            st.error(f"VOCÊ TEM CERTEZA QUE QUER EXCLUIR O SEU PLANO {st.session_state.projeto_ativo}?")
            ce1, ce2 = st.columns(2)
            if ce1.button("SIM", use_container_width=True):
                supabase.table("lancamentos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).execute()
                supabase.table("config_projetos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).execute()
                st.session_state.projeto_ativo = None
                st.session_state.confirmar_exclusao_plano = False
                st.rerun()
            if ce2.button("NÃO", use_container_width=True):
                st.session_state.confirmar_exclusao_plano = False
                st.rerun()
# --- RODAPÉ ---
st.divider()
# ITEM (5): Alteração da mensagem solicitada
st.caption("ORCAS v01 - Sistema Gestão de Planejamento Financeiro")