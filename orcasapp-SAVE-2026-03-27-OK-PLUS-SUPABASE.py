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
    #MainMenu {visibility: hidden;} 
    footer {visibility: hidden;}
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
                    # CHAVE MESTRA: Blindada contra cálculos de data
                    st.session_state.CHAVE_MESTRA_UUID = str(user_data['id'])
                    st.session_state.usuario = em
                    st.session_state.vencimento = str(user_data['vencimento'])
                    st.session_state.zap_ativo = user_data.get('zap_ativo', 0)
                    st.session_state.projeto_ativo = None
                    st.rerun()
                else:
                    st.error("E-mail ou senha incorretos.")
            
            if col_btn_l2.button("Esqueci minha Senha"):
                st.info("Por favor, entre em contato com o suporte administrativo do ORCAS.")

        with aba[1]:
            st.info("Para criar uma nova conta, entre em contato com o suporte administrativo do ORCAS.")
    st.stop()

# --- 4. ESTADO E DADOS ---
# Aqui definimos a variável que será usada em todo o script
ID_USUARIO_LOGADO = str(st.session_state.get('CHAVE_MESTRA_UUID', ''))
vencimento_str = st.session_state.get('vencimento', '2026-01-01')
venc_dt_objeto = datetime.strptime(vencimento_str, '%Y-%m-%d').date()

# SEGURANÇA: Passamos o ID e o cálculo de dias sem criar variáveis 'uid' perigosas
if ID_USUARIO_LOGADO:
    security.verificar_bloqueio_v01(ID_USUARIO_LOGADO, (venc_dt_objeto - datetime.now().date()).days)

# Busca de projetos usando o ID correto
projs_req = supabase.table("config_projetos").select("projeto_id").eq("usuario_id", ID_USUARIO_LOGADO).execute()
projs = [r['projeto_id'] for r in projs_req.data]

if 'projeto_ativo' not in st.session_state:
    st.session_state.projeto_ativo = None
if 'msg_sucesso' not in st.session_state:
    st.session_state.msg_sucesso = None
if 'confirmar_exclusao_ativa' not in st.session_state:
    st.session_state.confirmar_exclusao_ativa = False

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

# --- 5. BARRA LATERAL ---
with st.sidebar:
    st.markdown('<div class="logo-sidebar">🐋 ORCAS</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="user-email">👤 {st.session_state.usuario}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="venc-text">📅 EXPIRA EM: {venc_dt_objeto.strftime("%d/%m/%Y")}</div>', unsafe_allow_html=True)

    if st.session_state.projeto_ativo:
        st.markdown(f'<div class="project-tag-sidebar">Plano Ativo: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
        n_saldo_txt = st.text_input("Saldo Inicial", value=format_moeda(s_db))
        n_saldo_val = parse_moeda(n_saldo_txt)
        if n_saldo_val != s_db:
            dados_upsert = {
                "projeto_id": st.session_state.projeto_ativo, 
                "usuario_id": uid, 
                "saldo_inicial": n_saldo_val, 
                "data_ini": d_ini_db.strftime('%Y-%m-%d'), 
                "data_fim": d_fim_db.strftime('%Y-%m-%d')
            }
            check_exist = supabase.table("config_projetos").select("id").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).execute()
            if check_exist.data: 
                dados_upsert["id"] = check_exist.data[0]["id"]
            supabase.table("config_projetos").upsert(dados_upsert).execute()
            st.rerun()

    st.divider()
    menu_opcoes = ["🏠 Dashboard", "📑 Lançamentos", "📅 Projetar", "✅ Conciliação", "⚙️ Gestão", "📊 Admin"]
    idx_default = 4 if st.session_state.projeto_ativo is None else 0
    escolha = st.radio("Navegação", menu_opcoes, index=idx_default, label_visibility="collapsed")
    st.divider()
    if st.button("Sair do Sistema"):
        st.session_state.clear()
        st.rerun()

st.markdown("<div id='topo-ancora'></div>", unsafe_allow_html=True)

if st.session_state.projeto_ativo is None and escolha not in ["⚙️ Gestão", "📊 Admin"]:
    escolha = "⚙️ Gestão"

# --- 6. CARREGAMENTO DO DATAFRAME (CORRIGIDO) ---
# Substituímos o 'uid' que não existe mais por 'ID_USUARIO_LOGADO'
res_l = supabase.table("lancamentos").select("*").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", ID_USUARIO_LOGADO).order("data").execute()
df = pd.DataFrame(res_l.data)

if not df.empty:
    df.columns = [c.lower() for c in df.columns]
else:
    df = pd.DataFrame(columns=[
        'id', 'data', 'descricao', 'tipo', 'valor_plan', 'valor_real', 
        'status', 'permite_parcial', 'projeto_id', 'usuario_id', 
        'data_vencimento', 'id_pai', 'usar_media', 'complemento_texto',
        'correcao_freq', 'correcao_valor'
    ])
# --- TELA: DASHBOARD ---
if escolha == "🏠 Dashboard":
    st.markdown(f'<div class="titulo-tela">Dashboard: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    if not df.empty and 'data' in df.columns:
        # Preparação de dados para o gráfico de linha (Saldo Acumulado)
        df['dt'] = pd.to_datetime(df['data'])
        df['v'] = df.apply(
            lambda x: (x['valor_real'] if x['status'] == 'Realizado' else x['valor_plan']) * (1 if x['tipo'] == 'Entrada' else -1), 
            axis=1
        )
        
        df_diario = df.groupby('dt')['v'].sum().reset_index()
        df_diario = df_diario.sort_values('dt')
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
        
        fig_line.update_layout(
            title="Evolução do Saldo Projetado/Realizado", 
            height=350, 
            margin=dict(l=20, r=20, t=50, b=20), 
            hovermode="x unified"
        )
        st.plotly_chart(fig_line, use_container_width=True)
        
        st.subheader("Análise Mensal: Planejado x Realizado")
        df['MesAno'] = df['dt'].dt.strftime('%b/%y')
        
        res_mensal = df.groupby(['MesAno', 'tipo']).agg({'valor_plan':'sum', 'valor_real':'sum'}).reset_index()
        meses_ordem = df.sort_values('dt')['MesAno'].unique()
        
        fig_bar = go.Figure()
        cores_map = {
            'Entrada': {'p': '#A5D8FF', 'r': '#1E3A8A'}, 
            'Saída': {'p': '#FFA8A8', 'r': '#C53030'}
        }
        
        for tipo_mov in ['Entrada', 'Saída']:
            d_tipo = res_mensal[res_mensal['tipo'] == tipo_mov]
            if not d_tipo.empty:
                fig_bar.add_trace(go.Bar(
                    x=d_tipo['MesAno'], 
                    y=d_tipo['valor_plan'], 
                    name=f'{tipo_mov} Plan.', 
                    marker_color=cores_map[tipo_mov]['p'], 
                    offsetgroup=tipo_mov, 
                    width=0.3
                ))
                fig_bar.add_trace(go.Bar(
                    x=d_tipo['MesAno'], 
                    y=d_tipo['valor_real'], 
                    name=f'{tipo_mov} Real.', 
                    marker_color=cores_map[tipo_mov]['r'], 
                    offsetgroup=tipo_mov, 
                    width=0.15
                ))
        
        fig_bar.update_layout(
            barmode='group', 
            xaxis={'categoryorder':'array', 'categoryarray':meses_ordem}, 
            height=350
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("💡 Nenhum dado encontrado para gerar o Dashboard.")

# --- TELA: LANÇAMENTOS ---
# --- TELA: LANÇAMENTOS (INTEGRAÇÃO COMPLETA) ---
elif escolha == "📑 Lançamentos":
    st.markdown(f'<div class="titulo-tela">Lançamentos: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    if d_ini_db and d_fim_db:
        # Loop de meses e saldo acumulado original (83+ linhas mantidas)
        meses_periodo = []
        data_atual_loop = d_ini_db.replace(day=1)
        while data_atual_loop <= d_fim_db:
            meses_periodo.append(data_atual_loop.strftime('%Y-%m'))
            if data_atual_loop.month == 12: 
                data_atual_loop = data_atual_loop.replace(year=data_atual_loop.year + 1, month=1)
            else: 
                data_atual_loop = data_atual_loop.replace(month=data_atual_loop.month + 1)
        
        saldo_acumulado_mes = s_db
        
        for mes_str in meses_periodo:
            mask_mes = pd.to_datetime(df['data']).dt.strftime('%Y-%m') == mes_str
            df_mes = df[mask_mes].copy()
            
            entradas_mes = df_mes[df_mes['tipo'] == 'Entrada'].apply(
                lambda x: x['parcial_real'] if x['valor_plan'] == 0 else (x['valor_real'] if x['status'] == 'Realizado' else x['valor_plan']), axis=1
            ).sum()
            
            saidas_mes = df_mes[df_mes['tipo'] == 'Saída'].apply(
                lambda x: x['parcial_real'] if x['valor_plan'] == 0 else (x['valor_real'] if x['status'] == 'Realizado' else x['valor_plan']), axis=1
            ).sum()
                
            saldo_final_mes = saldo_acumulado_mes + entradas_mes - saidas_mes
            nome_mes_exibicao = datetime.strptime(mes_str, '%Y-%m').strftime('%m/%Y')
            
            with st.expander(f"📅 {nome_mes_exibicao} | Saldo Final: R$ {format_moeda(saldo_final_mes)}"):
                # Métricas do topo (originais)
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Saldo Inicial", f"R$ {format_moeda(saldo_acumulado_mes)}")
                col2.metric("Entradas (+)", f"R$ {format_moeda(entradas_mes)}")
                col3.metric("Saídas (-)", f"R$ {format_moeda(saidas_mes)}")
                col4.metric("Saldo Final", f"R$ {format_moeda(saldo_final_mes)}")
                st.divider()

                if not df_mes.empty:
                    # Cabeçalho da Lista
                    h1, h2, h3, h4, h5, h6 = st.columns([1.2, 3, 0.5, 1.2, 1.2, 0.8])
                    h1.write("**Data**"); h2.write("**Descrição**"); h3.write("**E/S**")
                    h4.write("**V. Plan**"); h5.write("**V. Real**"); h6.write("**Status**")

                    # Itens Pais (valor_plan > 0)
                    df_pais = df_mes[df_mes['valor_plan'] > 0].sort_values('data')
                    for _, row in df_pais.iterrows():
                        c1, c2, c3, c4, c5, c6 = st.columns([1.2, 3, 0.5, 1.2, 1.2, 0.8])
                        c1.write(pd.to_datetime(row['data']).strftime('%d/%m/%Y'))
                        c2.write(row['descricao'])
                        c3.write(row['tipo'][0])
                        c4.write(format_moeda(row['valor_plan']))
                        
                        v_acum = df_mes[df_mes['descricao'] == row['descricao']]['parcial_real'].sum()
                        c5.write(format_moeda(v_acum if v_acum > 0 else row['valor_real']))
                        c6.write('PLAN' if row['status'] == 'Planejado' else 'REAL')

                        # ASSOCIAÇÃO POR TEXTO (Filhos: valor_plan == 0)
                        filhos = df_mes[(df_mes['descricao'] == row['descricao']) & (df_mes['valor_plan'] == 0)]
                        for _, filho in filhos.iterrows():
                            f1, f2, f3, f4, f5, f6 = st.columns([1.2, 3, 0.5, 1.2, 1.2, 0.8])
                            f2.markdown(f"<span style='color:gray; padding-left:20px;'> >>> {pd.to_datetime(filho['parcial_data']).strftime('%d/%m/%y')}</span>", unsafe_allow_html=True)
                            f3.markdown(f"<span style='color:gray;'>{filho['tipo'][0]}</span>", unsafe_allow_html=True)
                            f5.markdown(f"<span style='color:gray;'>{format_moeda(filho['parcial_real'])}</span>", unsafe_allow_html=True)
                            f6.markdown(f"<span style='color:gray;'>REAL</span>", unsafe_allow_html=True)
                else:
                    st.write("ℹ️ Nenhum lançamento para este mês.")
            saldo_acumulado_mes = saldo_final_mes

    if st.button("Voltar ao Topo", key="btn_topo_lanc"): 
        ir_para_o_topo()

# --- TELA: PROJETAR ---
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
        f_p = c_f.date_input("Até", value=d_fim_db if d_fim_db else datetime.now().date(), format="DD/MM/YYYY", key="pj_data_fim")

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
                    if curr.day == dia_a and curr.month == mes_a: 
                        match_dm = True
                except: 
                    pass
            else:
                match_dm = (d_m == "" or d_m == "*" or str(curr.day) == d_m)

            if (d_e is None or curr == d_e) and match_dm and (d_s == "" or curr.weekday() == d_map[d_s]):
                dt_f = curr
                
                # SOLICITAÇÃO (2): Se permitir parciais, altera dia para 01 do mês/ano correspondente
                if permitir_parcial:
                    dt_f = dt_f.replace(day=1)
                elif fds != "Manter" and dt_f.weekday() >= 5: 
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

            if n_ocorrencias > 0 and gerados >= n_ocorrencias: 
                break
            curr += timedelta(days=1)
        
        if lista_bulk:
            supabase.table("lancamentos").insert(lista_bulk).execute()
            st.session_state.msg_sucesso = f"Sucesso! {len(lista_bulk)} lançamentos gerados."
            st.rerun()

    if btn_col2.button("Excluir", use_container_width=True):
        if not desc: 
            st.error("Informe a descrição para excluir os lançamentos correspondentes.")
        else:
            st.session_state.confirmar_exclusao_ativa = True
            st.rerun()
# --- TELA: CONCILIAÇÃO (SLIM FINAL + BLINDAGEM UUID TOTAL) ---
# --- TELA: CONCILIAÇÃO (BLINDAGEM TOTAL ANTI-365) ---
# --- TELA: CONCILIAÇÃO ---
elif escolha == "✅ Conciliação":
    st.markdown(f'<div class="titulo-tela">Conciliação: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    hoje_c = datetime.now().date()
    ini_mes_c = hoje_c.replace(day=1)
    limite_c = hoje_c - timedelta(days=3)

    df_c = df.copy()
    df_c['dt_obj'] = pd.to_datetime(df_c['data']).dt.date
    
    # Filtro de exibição conforme seu código enviado
    df_f = df_c[
        (df_c['dt_obj'] <= hoje_c) & 
        ((df_c['status'] == 'Planejado') | ((df_c['status'] == 'Realizado') & (df_c['dt_obj'] >= limite_c)))
    ].copy()

    parciais_topo = df_f[(df_f['permite_parcial'] == True) & (df_f['dt_obj'] >= ini_mes_c)]
    demais_itens = df_f[~df_f.index.isin(parciais_topo.index)].sort_values('dt_obj', ascending=False)
    df_final_concilia = pd.concat([parciais_topo, demais_itens])

    # Cabeçalho Compacto (Original)
    h1, h2, h3, h4, h5, h6 = st.columns([2.5, 0.5, 1.2, 1.8, 1.8, 1.2])
    h1.write("**Data - Descrição**")
    h2.write("**E/S**")
    h3.write("**V. Plan.**")
    h4.write("**V. Real**")
    h5.write("**Valor Parcial**")
    h6.write("**Ação**")
    st.divider()

    for _, row in df_final_concilia.iterrows():
        # SOMA PELO CAMPO DESCRIÇÃO (Apenas registros onde valor_plan é 0)
        v_acumulado_desc = df[df['descricao'] == row['descricao']]['parcial_real'].sum()
        cor_txt = "red" if v_acumulado_desc > row['valor_plan'] else "black"
        
        st.markdown('<div style="margin-bottom: -38px;"></div>', unsafe_allow_html=True)
        c1, c2, c3, c4, c5, c6 = st.columns([2.5, 0.5, 1.2, 1.8, 1.8, 1.2])
        
        c1.markdown(f"<span style='color:{cor_txt}'>{row['dt_obj'].strftime('%d/%m/%y')} - {row['descricao']}</span>", unsafe_allow_html=True)
        cor_tipo = 'red' if row['tipo'] == 'Saída' else 'blue'
        c2.markdown(f"<span style='color:{cor_tipo}'>{row['tipo'][0]}</span>", unsafe_allow_html=True)
        c3.write(format_moeda(row['valor_plan']))
        
        if row['permite_parcial']:
            c4.write(format_moeda(v_acumulado_desc))
            v_parc_in = c5.text_input("", key=f"p_{row['id']}", value="0,00", label_visibility="collapsed")
            
            if c6.button("Confirmar", key=f"btn_p_{row['id']}"):
                v_dig = parse_moeda(v_parc_in)
                if v_dig > 0:
                    # GRAVAÇÃO: Mesma descrição, data dia 01, valor_plan = 0
                    supabase.table("lancamentos").insert({
                        "projeto_id": str(st.session_state.projeto_ativo),
                        "usuario_id": str(st.session_state.get('CHAVE_MESTRA_UUID')), # Garante o vínculo do usuário logado
                        "descricao": row['descricao'], 
                        "data": ini_mes_c.strftime('%Y-%m-%d'), # Sempre dia 01
                        "data_vencimento": ini_mes_c.strftime('%Y-%m-%d'), # Resolve erro de constraint
                        "tipo": row['tipo'],
                        "valor_plan": 0,
                        "valor_real": 0,
                        "status": "Realizado",
                        "parcial_real": v_dig,
                        "parcial_data": hoje_c.strftime('%Y-%m-%d')
                    }).execute()
                    st.rerun()
        else:
            if row['status'] == 'Realizado':
                c4.write(format_moeda(row['valor_real']))
                c6.write("✅")
            else:
                v_norm_in = c4.text_input("", key=f"n_{row['id']}", value=format_moeda(row['valor_plan']), label_visibility="collapsed")
                if c6.button("Confirmar", key=f"btn_n_{row['id']}"):
                    supabase.table("lancamentos").update({
                        "valor_real": parse_moeda(v_norm_in), 
                        "status": "Realizado"
                    }).eq("id", row['id']).execute()
                    st.rerun()
        st.divider()
# --- TELA: GESTÃO (REGRAS DE DATAS) ---
elif escolha == "⚙️ Gestão":
    st.markdown('<div class="titulo-tela">Gestão de Projetos e Assinatura</div>', unsafe_allow_html=True)
    
    if st.session_state.msg_sucesso:
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    lista_gestao = ["-- Selecionar Plano --"] + projs
    plano_sel = st.selectbox("Trocar para outro Plano Financeiro:", lista_gestao)
    
    if plano_sel != "-- Selecionar Plano --" and plano_sel != st.session_state.projeto_ativo:
        st.session_state.projeto_ativo = plano_sel
        st.rerun()

    st.divider()
    
    st.subheader("Configuração do seu Plano Financeiro")
    nome_plano_input = st.text_input("Nome do Plano", value=st.session_state.projeto_ativo if st.session_state.projeto_ativo else "")
    
    # SOLICITAÇÃO (1): Datas só aparecem se houver plano selecionado ou nome digitado
    if nome_plano_input and nome_plano_input.strip() != "":
        col_g1, col_g2 = st.columns(2)
        d_ini_g = col_g1.date_input("Data de Início", value=d_ini_db if d_ini_db else hoje)
        d_fim_g = col_g2.date_input("Data de Término", value=d_fim_db if d_fim_db else hoje + timedelta(days=365))
        
        ativar_zap = st.checkbox("Ativar Notificações WhatsApp (+ R$ 10,00/mês)", value=(st.session_state.get('zap_ativo', 0) == 1))
        
        v_estimado = security.calcular_valor_v01(len(projs), d_ini_g.strftime('%Y-%m-%d'), d_fim_g.strftime('%Y-%m-%d'))
        if ativar_zap: v_estimado += 10.0
        
        st.info(f"💳 Valor da Assinatura: **R$ {format_moeda(v_estimado)} / mês**")
        
        if st.button("Salvar Alterações / Criar Plano", use_container_width=True):
            dados_p = {
                "projeto_id": nome_plano_input, "usuario_id": uid, "saldo_inicial": s_db,
                "data_ini": d_ini_g.strftime('%Y-%m-%d'), "data_fim": d_fim_g.strftime('%Y-%m-%d')
            }
            res_p = supabase.table("config_projetos").select("id").eq("projeto_id", nome_plano_input).eq("usuario_id", uid).execute()
            if res_p.data: dados_p["id"] = res_p.data[0]["id"]
            
            supabase.table("config_projetos").upsert(dados_p).execute()
            supabase.table("usuarios").update({"zap_ativo": 1 if ativar_zap else 0}).eq("id", uid).execute()
            st.session_state.projeto_ativo = nome_plano_input
            st.session_state.msg_sucesso = "Configurações atualizadas!"
            st.rerun()
    else:
        st.warning("Selecione um plano ou digite um nome para configurar as datas e assinatura.")

    if st.session_state.projeto_ativo:
        st.divider()
        if st.button("EXCLUIR ESTE PLANO DEFINITIVAMENTE", type="primary"):
            st.session_state.confirmar_exclusao_plano = True

        if st.session_state.get('confirmar_exclusao_plano', False):
            st.error(f"Deseja mesmo excluir o plano {st.session_state.projeto_ativo}?")
            ce1, ce2 = st.columns(2)
            if ce1.button("CONFIRMAR EXCLUSÃO"):
                supabase.table("lancamentos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).execute()
                supabase.table("config_projetos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).execute()
                st.session_state.projeto_ativo = None
                st.session_state.confirmar_exclusao_plano = False
                st.rerun()
            if ce2.button("CANCELAR"):
                st.session_state.confirmar_exclusao_plano = False
                st.rerun()

# --- TELA: ADMIN (LAYOUT EXCEL / SOLICITAÇÃO 4) ---
elif escolha == "📊 Admin":
    st.markdown('<div class="titulo-tela">Painel Administrativo: Lançamentos</div>', unsafe_allow_html=True)
    
    if df.empty:
        st.info("Nenhum dado disponível no plano atual.")
    else:
        # Colunas conforme solicitado (Todas as colunas da tabela)
        colunas_planilha = [
            'id', 'data', 'descricao', 'complemento_texto', 'tipo', 'valor_plan', 
            'valor_real', 'status', 'permite_parcial', 'data_vencimento', 
            'id_pai', 'usar_media', 'correcao_freq', 'correcao_valor'
        ]
        
        df_admin = df[colunas_planilha].copy()
        
        st.write("### Editor de Dados (Visualização Excel)")
        df_editado = st.data_editor(
            df_admin,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": st.column_config.TextColumn("ID", disabled=True),
                "data": st.column_config.DateColumn("Data"),
                "valor_plan": st.column_config.NumberColumn("Planejado", format="R$ %.2f"),
                "valor_real": st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Entrada", "Saída"]),
                "status": st.column_config.SelectboxColumn("Status", options=["Planejado", "Realizado"]),
                "permite_parcial": st.column_config.CheckboxColumn("Parcial?"),
            }
        )
        
        ca1, ca2 = st.columns(2)
        if ca1.button("💾 Salvar Alterações em Massa"):
            for _, r in df_editado.iterrows():
                id_item = r['id']
                # Converte para dict e remove o ID para o update
                dados_update = r.to_dict()
                del dados_update['id']
                # Garante que datas sejam strings
                if isinstance(dados_update['data'], (datetime, pd.Timestamp)):
                    dados_update['data'] = dados_update['data'].strftime('%Y-%m-%d')
                
                supabase.table("lancamentos").update(dados_update).eq("id", id_item).execute()
            st.success("Base de dados atualizada!"); st.rerun()
            
        if ca2.button("🗑️ Limpar Todos os Lançamentos", type="primary"):
            supabase.table("lancamentos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).execute()
            st.rerun()

# --- RODAPÉ ---
st.divider()
st.caption(f"ORCAS v01 | Usuário: {st.session_state.usuario} | Projeto: {st.session_state.projeto_ativo}")