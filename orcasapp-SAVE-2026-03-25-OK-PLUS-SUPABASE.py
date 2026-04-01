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
    df = pd.DataFrame(columns=['id', 'data', 'descricao', 'tipo', 'valor_plan', 'valor_real', 'status', 'permite_parcial'])

# --- TELA: DASHBOARD ---
if escolha == "🏠 Dashboard":
    st.markdown(f'<div class="titulo-tela">Dashboard: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    if not df.empty and 'data' in df.columns:
        df['dt'] = pd.to_datetime(df['data'])
        
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

# --- TELA: PROJETAR (VERSÃO PROJEÇÃO AVANÇADA) ---
elif escolha == "📅 Projetar":
    st.markdown(f'<div class="titulo-tela">Projetar: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    if st.session_state.msg_sucesso: 
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    col_d1, col_d2 = st.columns([4, 2])
    desc = col_d1.text_input("Descrição", key="pj_d")
    comp_txt = col_d2.text_input("Complemento", help="Será adicionado ao final da descrição")
    
    col_v, col_t = st.columns(2)
    v_t = col_v.text_input("Valor", "0,00")
    tipo = col_t.selectbox("Tipo", ["Saída", "Entrada"])

    with st.expander("Recorrência e Datas"):
        c1, c2, c3 = st.columns(3)
        d_m = c1.text_input("Dia (1-31, DD/MM ou *)", "")
        d_s = c2.selectbox("Dia da Semana", ["", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"])
        d_e = c3.date_input("Dia Específico", value=None, format="DD/MM/YYYY")
        
        n_ocorrencias = st.number_input("Nº de Ocorrências (0 = usar Data Até)", min_value=0, step=1)
        fds = st.radio("Se cair em Fim de Semana:", ["Manter", "Antecipa", "Posterga"], horizontal=True)
        
        c_i, c_f = st.columns(2)
        i_p = c_i.date_input("Início", value=datetime.now().date(), format="DD/MM/YYYY", key="pj_data_ini")
        f_p = c_f.date_input("Até", value=d_fim_db, format="DD/MM/YYYY", key="pj_data_fim")

    with st.expander("🛠️ Projeção Avançada", expanded=False):
        st.markdown("**Regras de Correção Automática**")
        col_c1, col_c2, col_c3 = st.columns([2, 2, 3])
        usar_corrc = col_c1.checkbox("Corrigir este valor?")
        c_quando = col_c2.selectbox("Quando:", ["Todo mês", "Todo ano"])
        c_base = col_c3.selectbox("Com base em:", ["Média dos Realizados", "Percentual Fixo (%)", "IGPM"])
        c_val_fixo = st.text_input("Valor do Percentual (se fixo)", "0,00")

        st.divider()

        st.markdown("**Realizações Parciais e Resíduos**")
        col_p1, col_p2, col_p3 = st.columns([2, 2, 3])
        permitir_parcial = col_p1.checkbox("Permitir parciais?")
        p_ate = col_p2.selectbox("Até:", ["Último dia do mês", "Último dia do ano", "Sempre"])
        p_depois = col_p3.selectbox("Depois disso:", [
            "Zera o Realizado", 
            "Adiciona a diferença no próximo Planejado",
            "Copia Planejado atualizado para o próximo"
        ])

    btn_col1, btn_col2, _ = st.columns([1, 1, 2])

    if btn_col1.button("Incluir", use_container_width=True):
        v = parse_moeda(v_t)
        v_pct = parse_moeda(c_val_fixo) / 100
        curr = i_p
        lista_bulk = [] 
        gerados = 0
        d_map = {"Segunda":0,"Terça":1,"Quarta":2,"Quinta":3,"Sexta":4,"Sábado":5,"Domingo":6}
        
        limite_loop = f_p if n_ocorrencias == 0 else i_p + timedelta(days=3650)

        while curr <= limite_loop:
            match_dm = False
            if "/" in d_m:
                try:
                    dia_a, mes_a = map(int, d_m.split("/"))
                    if curr.day == dia_a and curr.month == mes_a: match_dm = True
                except: pass
            else:
                match_dm = (d_m == "" or d_m == "*" or str(curr.day) == d_m)

            if (d_e is None or curr == d_e) and match_dm and (d_s == "" or curr.weekday() == d_map[d_s]):
                dt_f = curr
                if fds != "Manter" and dt_f.weekday() >= 5: 
                    dt_f += timedelta(days=(2 if dt_f.weekday()==5 else 1) if fds=="Posterga" else -1)
                
                nome_final = f"{desc} {comp_txt}".strip() if comp_txt else desc

                lista_bulk.append({
                    "projeto_id": st.session_state.projeto_ativo, 
                    "usuario_id": uid, 
                    "data": dt_f.strftime('%Y-%m-%d'), 
                    "data_vencimento": dt_f.strftime('%Y-%m-%d'),
                    "descricao": nome_final, 
                    "valor_plan": v, 
                    "valor_real": 0.0, 
                    "tipo": tipo, 
                    "status": 'Planejado',
                    "permite_parcial": permitir_parcial,
                    "usar_media": (usar_corrc and c_base == "Média dos Realizados"),
                    "complemento_texto": comp_txt if comp_txt else None,
                    "correcao_freq": c_quando if usar_corrc else None,
                    "correcao_valor": v_pct if c_base == "Percentual Fixo (%)" else 0.0
                })
                gerados += 1
                if usar_corrc and c_quando == "Todo mês" and c_base == "Percentual Fixo (%)":
                    v *= (1 + v_pct)

            if n_ocorrencias > 0 and gerados >= n_ocorrencias: break
            curr += timedelta(days=1)
        
        if lista_bulk:
            supabase.table("lancamentos").insert(lista_bulk).execute()
            st.session_state.msg_sucesso = f"Sucesso! {len(lista_bulk)} gerados."
            st.rerun()

    if btn_col2.button("Excluir", use_container_width=True):
        if not desc: st.error("Informe a descrição.")
        else:
            st.session_state.confirmar_exclusao_ativa = True
            st.rerun()
            # --- TELA: CONCILIAÇÃO (VERSÃO AVANÇADA) ---
elif escolha == "✅ Conciliação":
    st.markdown(f'<div class="titulo-tela">Conciliação: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)

    # 1. BUSCA DE DADOS E FILTRAGEM (Regra dos 3 dias)
    data_limite_retroativa = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    
    # Filtro: Planejados OU Realizados nos últimos 3 dias
    df_conciliacao = df[
        (df['status'] == 'Planejado') | 
        ((df['status'] == 'Realizado') & (df['data'] >= data_limite_retroativa))
    ].copy()

    # 2. SEPARAÇÃO POR CATEGORIAS
    parciais = df_conciliacao[df_conciliacao['permite_parcial'] == True]
    normais = df_conciliacao[df_conciliacao['permite_parcial'] == False].sort_values('data', ascending=False)

    # --- CABEÇALHO DA TABELA ---
    h1, h2, h3, h4, h5, h6 = st.columns([2, 1, 2, 2, 2, 2])
    h1.write("**Data - Descrição**")
    h2.write("**E/S**")
    h3.write("**Valor Plan.**")
    h4.write("**Valor Real**")
    h5.write("**Valor Parcial**")
    h6.write("**Ação**")
    st.divider()

    # 3. EXIBIÇÃO: LANÇAMENTOS PARCIAIS (NO TOPO)
    for _, row in parciais.iterrows():
        c1, c2, c3, c4, c5, c6 = st.columns([2, 1, 2, 2, 2, 2])
        
        data_dt = datetime.strptime(row['data'], '%Y-%m-%d')
        label_data = data_dt.strftime('%b/%y').upper()
        
        c1.write(f"{label_data} - {row['descricao']}")
        c2.markdown(f"<span style='color:{'red' if row['tipo']=='Saída' else 'blue'}'>{row['tipo'][0]}</span>", unsafe_allow_html=True)
        c3.write(format_moeda(row['valor_plan']))
        c4.write(format_moeda(row['valor_real']))
        
        v_parcial = c5.text_input("R$", key=f"part_{row['id']}", value="0,00")
        
        if c6.button("Confirmar", key=f"btn_{row['id']}"):
            valor_digitado = parse_moeda(v_parcial)
            if valor_digitado > 0:
                novo_realizado_total = row['valor_real'] + valor_digitado
                
                # Registro Filho (Extrato/Gráficos)
                supabase.table("lancamentos").insert({
                    "projeto_id": row['projeto_id'], "usuario_id": uid, "data": datetime.now().strftime('%Y-%m-%d'),
                    "descricao": f"Pcl: {row['descricao']}", "valor_real": valor_digitado, "status": "Realizado", 
                    "tipo": row['tipo'], "id_pai": row['id'] 
                }).execute()
                
                # Atualiza o Pai (Controle interno)
                supabase.table("lancamentos").update({"valor_real": novo_realizado_total}).eq("id", row['id']).execute()
                st.rerun()

    # 4. EXIBIÇÃO: LANÇAMENTOS NORMAIS (ORDEM CRONOLÓGICA)
    for _, row in normais.iterrows():
        c1, c2, c3, c4, c5, c6 = st.columns([2, 1, 2, 2, 2, 2])
        data_fmt = datetime.strptime(row['data'], '%Y-%m-%d').strftime('%d/%m/%y')
        c1.write(f"{data_fmt} - {row['descricao']}")
        c2.markdown(f"<span style='color:{'red' if row['tipo']=='Saída' else 'blue'}'>{row['tipo'][0]}</span>", unsafe_allow_html=True)
        c3.write(format_moeda(row['valor_plan']))
        
        if row['status'] == 'Realizado':
            c4.write(format_moeda(row['valor_real']))
            c5.write("-")
            c6.write("✅")
        else:
            c4.write("-")
            v_input = c5.text_input("R$", key=f"norm_{row['id']}", value=format_moeda(row['valor_plan']))
            if c6.button("OK", key=f"btn_ok_{row['id']}"):
                supabase.table("lancamentos").update({
                    "valor_real": parse_moeda(v_input), 
                    "status": "Realizado"
                }).eq("id", row['id']).execute()
                st.rerun()
        st.divider()

    # 5. REALIZAR SEM PLANEJAMENTO (RODAPÉ)
    st.markdown("---")
    with st.expander("➕ Realizar um valor sem ter o Planejamento", expanded=False):
        re_data = st.date_input("Data", value=datetime.now())
        re_desc = st.text_input("Descrição Novo Lançamento")
        re_tipo = st.selectbox("Tipo", ["Saída", "Entrada"], key="re_tipo")
        re_val = st.text_input("Valor Real", "0,00", key="re_val")
        
        if st.button("Confirmar Realizado Avulso"):
            supabase.table("lancamentos").insert({
                "projeto_id": st.session_state.projeto_ativo, "usuario_id": uid, "data": re_data.strftime('%Y-%m-%d'),
                "descricao": re_desc, "valor_real": parse_moeda(re_val), "status": "Realizado", "tipo": re_tipo
            }).execute()
            st.rerun()

# --- TELA: GESTÃO ---
elif escolha == "⚙️ Gestão":
    st.markdown('<div class="titulo-tela">Gestão de Projetos e Assinatura</div>', unsafe_allow_html=True)
    
    if st.session_state.msg_sucesso:
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    lista_opcoes = ["-- Selecionar Plano --"] + projs
    fluxo_selecionado = st.selectbox("Trocar para outro Plano Financeiro:", lista_opcoes)
    
    if fluxo_selecionado != "-- Selecionar Plano --" and fluxo_selecionado != st.session_state.projeto_ativo:
        st.session_state.projeto_ativo = fluxo_selecionado
        st.rerun()

    st.divider()
    
    st.subheader("Configuração do seu Plano Financeiro")
    nome_fluxo_input = st.text_input("Nome do Plano (Ex: Pessoal, Empresa X)", 
                                    value=st.session_state.projeto_ativo if st.session_state.projeto_ativo else "")
    
    col_g1, col_g2 = st.columns(2)
    data_ini_gestao = col_g1.date_input("Data de Início do Plano", value=d_ini_db, format="DD/MM/YYYY")
    data_fim_gestao = col_g2.date_input("Data de Término do Plano", value=d_fim_db, format="DD/MM/YYYY")
    
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
            
            if st.session_state.projeto_ativo or nome_fluxo_input:
                supabase.table("usuarios").update({"zap_ativo": 1 if ativar_zap else 0}).eq("id", uid).execute()
                st.session_state.zap_ativo = 1 if ativar_zap else 0
            
            st.session_state.projeto_ativo = nome_fluxo_input
            st.session_state.msg_sucesso = "✅ Configurações salvas!"
            st.rerun()
        else:
            st.error("Por favor, insira um nome para o plano.")

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
st.caption("ORCAS v01 - Sistema Gestão de Planejamento Financeiro")