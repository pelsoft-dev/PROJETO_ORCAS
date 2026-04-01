import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÃO, CSS E OCULTAR MENUS NATIVOS ---
st.set_page_config(page_title="Orcas", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    
    /* FIXAÇÃO DO HEADER */
    .fixed-header {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        background-color: #FFFFFF;
        z-index: 9999;
        padding: 10px 25px;
        border-bottom: 2px solid #f0f2f6;
        box-shadow: 0px 2px 5px rgba(0,0,0,0.05);
        height: 90px;
    }

    /* Ajuste para o conteúdo não ser 'atropelado' pelo header */
    .main-content {
        margin-top: 120px; 
    }

    .logo-container {
        white-space: nowrap;
        font-weight: bold;
        font-size: 1.8rem;
        margin-top: 5px;
    }

    .saldo-label {
        font-size: 0.8rem;
        color: #555;
        margin-bottom: 2px;
    }

    div[data-testid="stHorizontalBlock"] {
        align-items: center;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. FUNÇÕES DE BANCO E FORMATAÇÃO ---
def format_moeda(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def parse_moeda(texto):
    try:
        return float(str(texto).replace('.', '').replace(',', '.'))
    except:
        return 0.0

def init_db():
    conn = sqlite3.connect('orcas.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS lancamentos 
                 (id INTEGER PRIMARY KEY, data TEXT, descricao TEXT, 
                  valor_plan REAL, valor_real REAL, tipo TEXT, status TEXT)''')
    conn.commit()
    conn.close()

def ajustar_fds(data, regra):
    ds = data.weekday() 
    if ds < 5 or regra == "Manter": return data
    if regra == "Posterga": return data + timedelta(days=(7-ds))
    if regra == "Antecipa": return data - timedelta(days=(ds-4))
    return data

init_db()

# --- 3. ESTADOS DE SESSÃO ---
if 'd_mestre_ini' not in st.session_state:
    st.session_state.d_mestre_ini = datetime.now().date()
if 'd_mestre_fim' not in st.session_state:
    st.session_state.d_mestre_fim = (datetime.now() + timedelta(days=90)).date()

# --- 4. HEADER FIXO ---
st.markdown('<div class="fixed-header">', unsafe_allow_html=True)
c1, c2, c3 = st.columns([1.5, 1.5, 4.5])

with c1:
    st.markdown('<div class="logo-container">🐋 ORCAS</div>', unsafe_allow_html=True)

with c2:
    st.markdown('<p class="saldo-label">saldo inicial</p>', unsafe_allow_html=True)
    s_ini_txt = st.text_input("Saldo Inicial", value="0,00", label_visibility="collapsed")
    saldo_inicial = parse_moeda(s_ini_txt)

with c3:
    escolha = st.radio("", ["🏠 Dashboard", "📅 Projetar", "✅ Conciliação", "⚙️ Gestão"], 
                       horizontal=True, label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="main-content">', unsafe_allow_html=True)

# --- 5. LÓGICA DAS TELAS ---
hoje = datetime.now().date()

if escolha == "⚙️ Gestão":
    st.subheader("Configurações do Fluxo")
    col_g1, col_g2 = st.columns(2)
    st.session_state.d_mestre_ini = col_g1.date_input("Início", value=st.session_state.d_mestre_ini, format="DD/MM/YYYY")
    st.session_state.d_mestre_fim = col_g2.date_input("Término", value=st.session_state.d_mestre_fim, format="DD/MM/YYYY")

elif escolha == "🏠 Dashboard":
    conn = sqlite3.connect('orcas.db')
    df = pd.read_sql_query("SELECT * FROM lancamentos ORDER BY data ASC", conn)
    conn.close()
    if not df.empty:
        df['data_dt'] = pd.to_datetime(df['data'])
        df['v'] = df.apply(lambda x: x['valor_real'] if x['valor_real'] > 0 else x['valor_plan'], axis=1)
        df['v_sinal'] = df.apply(lambda x: x['v'] if x['tipo'] == 'Entrada' else -x['v'], axis=1)
        df['Saldo_Acum'] = df['v_sinal'].cumsum() + saldo_inicial
        st.line_chart(df.set_index('data_dt')['Saldo_Acum'], height=200)
        df['Mes_Ano'] = df['data_dt'].dt.strftime('%Y-%m')
        saldo_transitado = saldo_inicial
        for mes_ref in sorted(df['Mes_Ano'].unique()):
            with st.expander(f"📅 {datetime.strptime(mes_ref, '%Y-%m').strftime('%m/%Y')}", expanded=True):
                m_df = df[df['Mes_Ano'] == mes_ref].copy()
                m_df['Data'] = m_df['data_dt'].dt.strftime('%d/%m/%Y')
                m_df['Planejado'] = m_df['valor_plan'].apply(format_moeda)
                m_df['Realizado'] = m_df['valor_real'].apply(format_moeda)
                st.table(m_df[['Data', 'descricao', 'tipo', 'Planejado', 'Realizado']])
                ent = m_df[m_df['tipo'] == 'Entrada']['v'].sum()
                sai = m_df[m_df['tipo'] == 'Saída']['v'].sum()
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Anterior", format_moeda(saldo_transitado))
                c2.metric("Entradas", format_moeda(ent))
                c3.metric("Saídas", format_moeda(sai))
                saldo_final_mes = saldo_transitado + (ent - sai)
                c4.metric("Saldo Final", format_moeda(saldo_final_mes))
                saldo_transitado = saldo_final_mes

elif escolha == "📅 Projetar":
    with st.container():
        col1, col2, col3 = st.columns(3)
        with col1:
            desc = st.text_input("Descrição")
            v_txt = st.text_input("Valor", value="0,00")
            tipo = st.selectbox("E/S", ["Entrada", "Saída"])
        with col2:
            dia_mes = st.text_input("Dia do Mês (1-31 ou *)")
            dia_sem = st.selectbox("Dia da Semana", ["", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"])
            dia_esp = st.date_input("Dia Específico", value=None, format="DD/MM/YYYY")
        with col3:
            d_ini = st.date_input("Início", value=st.session_state.d_mestre_ini, format="DD/MM/YYYY")
            d_fim = st.date_input("Até", value=st.session_state.d_mestre_fim, format="DD/MM/YYYY")
            regra_fds = st.radio("Fim de Semana", ["Manter", "Antecipa", "Posterga"], horizontal=True)

        c_b1, c_b2, c_res = st.columns([0.5, 0.5, 4])
        
        # VALIDAÇÃO DE DATA MESTRE
        if d_fim > st.session_state.d_mestre_fim:
            st.error(f"⚠️ A data de término não pode ser maior que {st.session_state.d_mestre_fim.strftime('%d/%m/%Y')} (definida na Gestão).")
        else:
            if c_b1.button("Incluir"):
                valor = parse_moeda(v_txt)
                conn = sqlite3.connect('orcas.db')
                curr = d_ini
                cont = 0
                dias_map = {"Segunda": "Monday", "Terça": "Tuesday", "Quarta": "Wednesday", "Quinta": "Thursday", "Sexta": "Friday", "Sábado": "Saturday", "Domingo": "Sunday"}
                while curr <= d_fim:
                    match = (dia_esp and curr == dia_esp) or (dia_mes == "*") or (dia_mes and str(curr.day) == dia_mes) or (dia_sem != "" and curr.strftime('%A') == dias_map.get(dia_sem, ""))
                    if match:
                        dt_f = ajustar_fds(curr, regra_fds).strftime('%Y-%m-%d')
                        conn.execute("INSERT INTO lancamentos (data, descricao, valor_plan, valor_real, tipo, status) VALUES (?,?,?,?,?,?)", (dt_f, desc, valor, 0.0, tipo, 'Planejado'))
                        cont += 1
                    curr += timedelta(days=1)
                conn.commit() ; conn.close()
                c_res.success(f"✅ {cont} lançamentos incluídos!")

        if c_b2.button("Excluir"):
            conn = sqlite3.connect('orcas.db')
            cursor = conn.execute("DELETE FROM lancamentos WHERE descricao = ? AND tipo = ? AND data BETWEEN ? AND ?", (desc, tipo, d_ini.strftime('%Y-%m-%d'), d_fim.strftime('%Y-%m-%d')))
            cont = cursor.rowcount
            conn.commit() ; conn.close()
            c_res.warning(f"🗑️ {cont} lançamentos excluídos!")

elif escolha == "✅ Conciliação":
    conn = sqlite3.connect('orcas.db')
    df_c = pd.read_sql_query("SELECT * FROM lancamentos WHERE data <= ? ORDER BY data ASC", conn, params=(hoje.strftime('%Y-%m-%d'),))
    conn.close()
    if not df_c.empty:
        c_h = st.columns([1, 2.5, 0.4, 0.8, 0.8, 0.3])
        for col, lab in zip(c_h, ["Data", "Descrição", "E/S", "Plan", "Real", "V"]): col.write(f"**{lab}**")
        for i, row in df_c.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([1, 2.5, 0.4, 0.8, 0.8, 0.3])
            dt_obj = datetime.strptime(row['data'], '%Y-%m-%d').date()
            if dt_obj < hoje and row['valor_real'] == 0:
                c1.markdown(f":red[{dt_obj.strftime('%d/%m/%Y')}]")
            else:
                c1.text(dt_obj.strftime('%d/%m/%Y'))
            c2.text(row['descricao'])
            c3.text(row['tipo'][0])
            c4.text(format_moeda(row['valor_plan']))
            val_input = c5.text_input("", value=format_moeda(row['valor_real']), key=f"r_{row['id']}", label_visibility="collapsed")
            novo_val = parse_moeda(val_input)
            if novo_val != row['valor_real']:
                conn = sqlite3.connect('orcas.db')
                conn.execute("UPDATE lancamentos SET valor_real = ?, status = 'Realizado' WHERE id = ?", (novo_val, row['id']))
                conn.commit() ; conn.close() ; st.rerun()
            if c6.button("✔️", key=f"b_{row['id']}"):
                conn = sqlite3.connect('orcas.db')
                conn.execute("UPDATE lancamentos SET valor_real = valor_plan, status = 'Realizado' WHERE id = ?", (row['id'],))
                conn.commit() ; conn.close() ; st.rerun()
    else:
        st.info("Nenhum lançamento pendente até hoje.")

st.markdown('</div>', unsafe_allow_html=True)