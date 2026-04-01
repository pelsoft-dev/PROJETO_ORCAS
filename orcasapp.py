import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import hashlib
import plotly.graph_objects as go
import streamlit.components.v1 as components

# --- 1. CONFIGURAÇÃO E ESTILO ---
st.set_page_config(page_title="ORCAS", layout="wide", initial_sidebar_state="expanded")

def ir_para_o_topo():
    components.html("""
        <script>
            window.parent.document.getElementById('topo-ancora').scrollIntoView();
        </script>
    """, height=0)

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
    </style>
""", unsafe_allow_html=True)

def format_moeda(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
def parse_moeda(t):
    try:
        t = str(t).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        return float(t)
    except: return 0.0

# --- 2. BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('orcas_saas.db')
    conn.execute('CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY, email TEXT UNIQUE, senha TEXT, vencimento TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS lancamentos (id INTEGER PRIMARY KEY, projeto_id TEXT, usuario_id INTEGER, data TEXT, descricao TEXT, valor_plan REAL, valor_real REAL, tipo TEXT, status TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS config_projetos (projeto_id TEXT, usuario_id INTEGER, saldo_inicial REAL, data_ini TEXT, data_fim TEXT, PRIMARY KEY (projeto_id, usuario_id))')
    conn.commit(); conn.close()
init_db()

# --- 3. LOGIN ---
if 'logado' not in st.session_state: st.session_state.logado = False
if not st.session_state.logado:
    st.markdown("<h1 style='text-align: center; margin-top: 50px;'>🐋 ORCAS</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        aba = st.tabs(["Entrar", "Criar Conta"])
        with aba[0]:
            em = st.text_input("E-mail"); se = st.text_input("Senha", type="password")
            col_b1, col_b2 = st.columns(2)
            if col_b1.button("Acessar"):
                sh = hashlib.sha256(str.encode(se)).hexdigest()
                conn = sqlite3.connect('orcas_saas.db')
                u = conn.execute("SELECT id, vencimento FROM usuarios WHERE email=? AND senha=?", (em, sh)).fetchone()
                conn.close()
                if u: 
                    st.session_state.logado, st.session_state.user_id, st.session_state.usuario, st.session_state.vencimento = True, u[0], em, u[1]
                    st.session_state.projeto_ativo = None
                    st.rerun()
                else: st.error("Login inválido.")
            if col_b2.button("Esqueci minha senha"): st.info("Suporte: suporte@orcas.com")
        with aba[1]:
            nem = st.text_input("Novo E-mail"); nse = st.text_input("Nova Senha", type="password")
            if st.button("Criar Conta (7 dias free)"):
                try:
                    conn = sqlite3.connect('orcas_saas.db')
                    venc = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
                    cur = conn.cursor()
                    cur.execute("INSERT INTO usuarios (email, senha, vencimento) VALUES (?,?,?)", (nem, hashlib.sha256(str.encode(nse)).hexdigest(), venc))
                    new_id = cur.lastrowid; conn.commit(); conn.close()
                    st.session_state.logado, st.session_state.user_id, st.session_state.usuario, st.session_state.vencimento = True, new_id, nem, venc
                    st.session_state.projeto_ativo = None
                    st.rerun()
                except: st.error("E-mail já cadastrado.")
    st.stop()

# --- 4. ESTADO E DADOS ---
uid = st.session_state.user_id
conn = sqlite3.connect('orcas_saas.db')
projs = [r[0] for r in conn.execute("SELECT DISTINCT projeto_id FROM config_projetos WHERE usuario_id=?", (uid,)).fetchall()]
conn.close()

if 'projeto_ativo' not in st.session_state:
    st.session_state.projeto_ativo = None

if 'msg_sucesso' not in st.session_state: st.session_state.msg_sucesso = None
if 'confirmar_exclusao_ativa' not in st.session_state: st.session_state.confirmar_exclusao_ativa = False

s_db = 0.0
d_ini_db = datetime.now().date()
d_fim_db = (datetime.now() + timedelta(days=730)).date()

if st.session_state.projeto_ativo:
    conn = sqlite3.connect('orcas_saas.db')
    cfg = conn.execute("SELECT saldo_inicial, data_ini, data_fim FROM config_projetos WHERE projeto_id=? AND usuario_id=?", (st.session_state.projeto_ativo, uid)).fetchone()
    conn.close()
    if cfg:
        s_db = cfg[0] if cfg[0] is not None else 0.0
        if cfg[1]: d_ini_db = datetime.strptime(cfg[1], '%Y-%m-%d').date()
        if cfg[2]: d_fim_db = datetime.strptime(cfg[2], '%Y-%m-%d').date()

venc_dt = datetime.strptime(st.session_state.vencimento, '%Y-%m-%d').date()
dias_rest = (venc_dt - datetime.now().date()).days

# --- BARRA LATERAL ---
with st.sidebar:
    st.markdown('<div class="logo-sidebar">🐋 ORCAS</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="user-email">👤 {st.session_state.usuario}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="venc-text">⏳ {max(0, dias_rest)} DIAS DE TESTES RESTANTE</div>', unsafe_allow_html=True)
    
    if st.session_state.projeto_ativo:
        st.markdown(f'<div class="project-tag-sidebar">Fluxo: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
        n_saldo = st.text_input("Saldo Inicial", value=format_moeda(s_db))
        if parse_moeda(n_saldo) != s_db:
            conn = sqlite3.connect('orcas_saas.db')
            conn.execute("INSERT OR REPLACE INTO config_projetos VALUES (?,?,?,?,?)", (st.session_state.projeto_ativo, uid, parse_moeda(n_saldo), d_ini_db.strftime('%Y-%m-%d'), d_fim_db.strftime('%Y-%m-%d')))
            conn.commit(); conn.close(); st.rerun()
    
    menu_opcoes = ["🏠 Dashboard", "📑 Lançamentos", "📅 Projetar", "✅ Conciliação", "⚙️ Gestão"]
    idx_inicial = 4 if st.session_state.projeto_ativo is None else 0
    escolha = st.radio("Menu", menu_opcoes, index=idx_inicial, label_visibility="collapsed")

    if "menu_ant" not in st.session_state: st.session_state.menu_ant = escolha
    if st.session_state.menu_ant != escolha:
        st.session_state.menu_ant = escolha
        ir_para_o_topo()

    if st.button("Sair"): st.session_state.logado = False; st.rerun()

st.markdown("<div id='topo-ancora'></div>", unsafe_allow_html=True)

if st.session_state.projeto_ativo is None:
    escolha = "⚙️ Gestão"

conn = sqlite3.connect('orcas_saas.db')
df = pd.read_sql_query("SELECT * FROM lancamentos WHERE projeto_id=? AND usuario_id=? ORDER BY data ASC", conn, params=(st.session_state.projeto_ativo, uid))
conn.close()

# --- TELAS ---
if escolha == "🏠 Dashboard":
    st.markdown(f'<div class="titulo-tela">Dashboard: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    if not df.empty:
        df['dt'] = pd.to_datetime(df['data'])
        df['v'] = df.apply(lambda x: (x['valor_real'] if x['status'] == 'Realizado' else x['valor_plan']) * (1 if x['tipo'] == 'Entrada' else -1), axis=1)
        df_d = df.groupby('dt')['v'].sum().reset_index()
        df_d['Saldo'] = df_d['v'].cumsum() + s_db
        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(x=df_d['dt'], y=df_d['Saldo'], mode='lines', name='Saldo Acumulado', line=dict(color='#1E3A8A', width=3), fill='tozeroy', fillcolor='rgba(30, 58, 138, 0.1)'))
        fig_line.update_layout(title="Evolução do Saldo Disponível", margin=dict(l=20, r=20, t=40, b=20), height=300)
        st.plotly_chart(fig_line, use_container_width=True)
        
        # --- RESTAURAÇÃO DO GRÁFICO 2 ---
        st.subheader("Planejado x Realizado (Mensal)")
        df['MesAno'] = df['dt'].dt.strftime('%b/%y')
        res = df.groupby(['MesAno', 'tipo']).agg({'valor_plan':'sum', 'valor_real':'sum'}).reset_index()
        meses_ordem = df.sort_values('dt')['MesAno'].unique()
        fig_bar = go.Figure()
        cores = {'Entrada': {'p': '#A5D8FF', 'r': '#1E3A8A'}, 'Saída': {'p': '#FFA8A8', 'r': '#C53030'}}
        for t in ['Entrada', 'Saída']:
            d_p = res[res['tipo'] == t]
            fig_bar.add_trace(go.Bar(x=d_p['MesAno'], y=d_p['valor_plan'], name=f'{t} Plan.', marker_color=cores[t]['p'], offsetgroup=t, width=0.3))
            fig_bar.add_trace(go.Bar(x=d_p['MesAno'], y=d_p['valor_real'], name=f'{t} Real.', marker_color=cores[t]['r'], offsetgroup=t, width=0.15))
        fig_bar.update_layout(barmode='group', xaxis={'categoryorder':'array', 'categoryarray':meses_ordem}, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_bar, use_container_width=True)
    else: st.info("Crie seu primeiro fluxo na aba Gestão para visualizar o Dashboard.")

elif escolha == "📑 Lançamentos":
    st.markdown(f'<div class="titulo-tela">Lançamentos: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    if not df.empty:
        df['dt'] = pd.to_datetime(df['data']); df['MesAno'] = df['dt'].dt.strftime('%Y-%m')
        s_acum = s_db; hoje_m = datetime.now().strftime('%Y-%m')
        for mes in sorted(df['MesAno'].unique()):
            m_df = df[df['MesAno'] == mes].copy()
            ent = m_df[m_df['tipo'] == 'Entrada']['valor_plan'].sum(); sai = m_df[m_df['tipo'] == 'Saída']['valor_plan'].sum(); s_fin = s_acum + ent - sai
            with st.expander(f"📅 {datetime.strptime(mes, '%Y-%m').strftime('%m/%Y')} | Final: R$ {format_moeda(s_fin)}", expanded=(mes >= hoje_m)):
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Inicial", format_moeda(s_acum)); c2.metric("Entradas", format_moeda(ent))
                c3.metric("Saídas", format_moeda(sai)); c4.metric("Final", format_moeda(s_fin))
                m_df['Data'] = m_df['dt'].dt.strftime('%d/%m/%Y')
                m_df['V. Plan.'] = m_df['valor_plan'].apply(format_moeda); m_df['V. Real'] = m_df['valor_real'].apply(format_moeda)
                st.table(m_df[['Data', 'descricao', 'tipo', 'V. Plan.', 'V. Real', 'status']])
            s_acum = s_fin

elif escolha == "📅 Projetar":
    st.markdown(f'<div class="titulo-tela">Projetar: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    if st.session_state.msg_sucesso: st.success(st.session_state.msg_sucesso); st.session_state.msg_sucesso = None
    if st.session_state.confirmar_exclusao_ativa:
        ir_para_o_topo()
        desc_sel = st.session_state.get('pj_d', '')
        d_esp = st.session_state.get('pj_data_especifica')
        if d_esp: msg = f"⚠️ Excluir '{desc_sel}' do dia {d_esp.strftime('%d/%m/%Y')}?"
        else: msg = f"⚠️ Excluir '{desc_sel}' no período de {st.session_state.pj_data_ini.strftime('%d/%m/%Y')} a {st.session_state.pj_data_fim.strftime('%d/%m/%Y')}?"
        st.warning(msg)
        cs, cn = st.columns(2)
        if cs.button("SIM"):
            conn = sqlite3.connect('orcas_saas.db')
            if d_esp: cur = conn.execute("DELETE FROM lancamentos WHERE projeto_id=? AND usuario_id=? AND descricao=? AND data=?", (st.session_state.projeto_ativo, uid, desc_sel, d_esp.strftime('%Y-%m-%d')))
            else: cur = conn.execute("DELETE FROM lancamentos WHERE projeto_id=? AND usuario_id=? AND descricao=? AND data BETWEEN ? AND ?", (st.session_state.projeto_ativo, uid, desc_sel, st.session_state.pj_data_ini.strftime('%Y-%m-%d'), st.session_state.pj_data_fim.strftime('%Y-%m-%d')))
            st.session_state.msg_sucesso = f"Sucesso! {cur.rowcount} excluído(s)."; conn.commit(); conn.close(); st.session_state.confirmar_exclusao_ativa = False; ir_para_o_topo(); st.rerun()
        if cn.button("NÃO"): st.session_state.confirmar_exclusao_ativa = False; st.rerun()

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
    if b1.button("Incluir"):
        v = parse_moeda(v_t); conn = sqlite3.connect('orcas_saas.db'); curr = i_p; cont = 0
        d_map = {"Segunda":0,"Terça":1,"Quarta":2,"Quinta":3,"Sexta":4,"Sábado":5,"Domingo":6}
        while curr <= f_p:
            match = (d_e is None or curr == d_e) and (d_m == "" or d_m == "*" or str(curr.day) == d_m) and (d_s == "" or curr.weekday() == d_map[d_s])
            if match:
                dt_f = curr
                if d_m == "*" and dt_f.weekday() >= 5 and fds != "Manter": pass 
                else:
                    if fds != "Manter" and dt_f.weekday() >= 5: dt_f += timedelta(days=(2 if dt_f.weekday()==5 else 1) if fds=="Posterga" else -1)
                    conn.execute("INSERT INTO lancamentos (projeto_id, usuario_id, data, descricao, valor_plan, valor_real, tipo, status) VALUES (?,?,?,?,?,?,?,?)", (st.session_state.projeto_ativo, uid, dt_f.strftime('%Y-%m-%d'), desc, v, 0.0, tipo, 'Planejado'))
                    cont += 1
            curr += timedelta(days=1)
        conn.commit(); conn.close(); st.session_state.msg_sucesso = f"Sucesso! {cont} incluídos."; ir_para_o_topo(); st.rerun()
    if b2.button("Excluir"):
        if not desc: st.error("Informe a descrição.")
        else: st.session_state.confirmar_exclusao_ativa = True; st.rerun()

elif escolha == "✅ Conciliação":
    st.markdown(f'<div class="titulo-tela">Conciliação: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    if st.session_state.msg_sucesso: st.success(st.session_state.msg_sucesso); st.session_state.msg_sucesso = None
    
    # Cabeçalho com proporções corrigidas para não quebrar o botão
    hc1, hc2, hc3, hc4, hc5 = st.columns([2.2, 0.4, 1.1, 1.1, 1.2])
    hc1.markdown("**Data - Descrição**")
    hc2.markdown("**E/S**")
    hc3.markdown("**Valor Plan.**")
    hc4.markdown("**Valor Real**")
    hc5.markdown("**Ação**")
    st.divider()

    df_c = df[pd.to_datetime(df['data']).dt.date <= datetime.now().date()].sort_values('data', ascending=False)
    if not df_c.empty:
        for _, r in df_c.iterrows():
            c1, c2, c3, c4, c5 = st.columns([2.2, 0.4, 1.1, 1.1, 1.2])
            c1.write(f"{datetime.strptime(r['data'], '%Y-%m-%d').strftime('%d/%m/%Y')} - {r['descricao']}")
            
            sigla = "E" if r['tipo'] == 'Entrada' else "S"
            cor = "blue" if sigla == "E" else "red"
            c2.markdown(f"<b style='color:{cor}'>{sigla}</b>", unsafe_allow_html=True)
            
            c3.write(f"R$ {format_moeda(r['valor_plan'])}")
            
            if r['status'] == 'Planejado':
                vr = c4.text_input("R$", value="", key=f"v{r['id']}", label_visibility="collapsed", placeholder="0,00")
                if c5.button("Confirmar", key=f"b{r['id']}"):
                    fv = parse_moeda(vr) if vr.strip() != "" else r['valor_plan']
                    conn = sqlite3.connect('orcas_saas.db')
                    conn.execute("UPDATE lancamentos SET valor_real=?, status='Realizado' WHERE id=?", (fv, r['id']))
                    conn.commit(); conn.close()
                    st.session_state.msg_sucesso = "Conciliado!"
                    ir_para_o_topo(); st.rerun()
            else:
                c4.write(f"R$ {format_moeda(r['valor_real'])}")
                c5.write("✅ OK")
    else: st.info("Nada para conciliar.")

elif escolha == "⚙️ Gestão":
    st.markdown(f'<div class="titulo-tela">Gestão: {st.session_state.projeto_ativo if st.session_state.projeto_ativo else "Novo Fluxo"}</div>', unsafe_allow_html=True)
    if st.session_state.msg_sucesso: st.success(st.session_state.msg_sucesso); st.session_state.msg_sucesso = None
    sel = st.selectbox("Escolher Fluxo Existente", [""] + projs, index=0)
    if sel and sel != st.session_state.projeto_ativo: 
        st.session_state.projeto_ativo = sel
        ir_para_o_topo(); st.rerun()
    st.divider()
    nn = st.text_input("Nome do Fluxo", value=st.session_state.projeto_ativo if st.session_state.projeto_ativo else "")
    c1, c2 = st.columns(2)
    ni, nf = c1.date_input("Início", value=d_ini_db, format="DD/MM/YYYY"), c2.date_input("Término", value=d_fim_db, format="DD/MM/YYYY")
    if st.button("Salvar Alterações e Carregar"):
        if nn:
            conn = sqlite3.connect('orcas_saas.db')
            conn.execute("INSERT OR REPLACE INTO config_projetos VALUES (?,?,?,?,?)", (nn, uid, s_db, ni.strftime('%Y-%m-%d'), nf.strftime('%Y-%m-%d')))
            conn.commit(); conn.close(); st.session_state.projeto_ativo = nn; st.session_state.msg_sucesso = "Salvo com sucesso!"; ir_para_o_topo(); st.rerun()
        else: st.error("Por favor, informe um nome para o fluxo.")