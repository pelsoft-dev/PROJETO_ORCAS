import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO E CSS ---
st.set_page_config(page_title="Orcas", layout="wide", initial_sidebar_state="collapsed")

def tem_atraso():
    try:
        conn = sqlite3.connect('orcas.db')
	hoje_str = datetime.now().strftime('%Y-%m-%d')
	res = conn.execute("SELECT COUNT(*) FROM lancamentos WHERE data < ? AND valor_real = 0", (hoje_str,)).fetchone()[0]
	conn.close()
	return res > 0
    except: return False

st.markdown("""

<style>
#MainMenu {visibility: hidden;} header {visibility: hidden;} footer {visibility: hidden;}
 stDeployButton {display:none;}
 fixed-header {
    position: fixed; top: 0; left: 0; width: 100%; background-color: white;
    z-index: 1000; padding: 5px 20px 0px 20px; border-bottom: 3px solid #333;
}
 main-content { margin-top: 85px; }
 mini-label { font-size: 11px; color: #666; margin-bottom: -15px; text-transform: lowercase; font-weight: bold; }
</style>

""", unsafe_allow_html=True)

# --- FUNÇÕES ---
def format_moeda(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
def parse_moeda(t):
    try: return float(str(t).replace('.', '').replace(',', '.'))
    except: return 0.0

def init_db():
    conn = sqlite3.connect('orcas.db')
    conn.execute('CREATE TABLE IF NOT EXISTS lancamentos (id INTEGER PRIMARY KEY, data TEXT, descricao TEXT, valor_plan REAL, valor_real REAL, tipo TEXT, status TEXT)')
    conn.commit() ; conn.close()

init_db()

# --- HEADER FIXO ---
st.markdown('<div class="fixed-header">', unsafe_allow_html=True)
c1, c2, c3 = st.columns([0.8, 1.2, 5])
with c1: st.markdown("<h2 style='margin:0; padding-top:10px;'>ORCAS</h2>", unsafe_allow_html=True)
with c2:
    st.markdown('<p class="mini-label">saldo inicial</p>', unsafe_allow_html=True)
    saldo_inicial = parse_moeda(st.text_input("", value="0,00", key="s_ini", label_visibility="collapsed"))
with c3:
    label_c = "🚨 Conciliação" if tem_atraso() else "✅ Conciliação"
    escolha = st.radio("", ["🏠 Dashboard", "📅 Projetar / Excluir", label_c], horizontal=True, label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

# --- CONTEÚDO ---
st.markdown('<div class="main-content">', unsafe_allow_html=True)
hoje = datetime.now().date()

if "Conciliação" in escolha:
    conn = sqlite3.connect('orcas.db')
    df = pd.read_sql_query("SELECT * FROM lancamentos WHERE data <= ? ORDER BY data ASC", conn, params=(hoje.strftime('%Y-%m-%d'),))
    if not df.empty:
        for i, row in df.iterrows():
            col = st.columns([1, 2.5, 0.8, 1, 0.3])
            dt = datetime.strptime(row['data'], '%Y-%m-%d').date()
            if dt < hoje and row['valor_real'] == 0: col[0].markdown(f":red[{dt.strftime('%d/%m/%Y')}]")
            else: col[0].text(dt.strftime('%d/%m/%Y'))
            col[1].text(row['descricao'])
            col[2].text(format_moeda(row['valor_plan']))
            v_in = col[3].text_input("", value=format_moeda(row['valor_real']), key=f"r_{row['id']}", label_visibility="collapsed")
            if parse_moeda(v_in) != row['valor_real']:
                conn.execute("UPDATE lancamentos SET valor_real = ? WHERE id = ?", (parse_moeda(v_in), row['id']))
                conn.commit() ; st.rerun()
            if col[4].button("✔️", key=f"b_{row['id']}"):
                conn.execute("UPDATE lancamentos SET valor_real = valor_plan WHERE id = ?", (row['id'],))
                conn.commit() ; st.rerun()
    conn.close()

elif escolha == "🏠 Dashboard":
    conn = sqlite3.connect('orcas.db')
    df = pd.read_sql_query("SELECT * FROM lancamentos ORDER BY data ASC", conn)
    if not df.empty:
        df['dt'] = pd.to_datetime(df['data'])
        df['v'] = df.apply(lambda x: x['valor_real'] if x['valor_real'] > 0 else x['valor_plan'], axis=1)
        df['vs'] = df.apply(lambda x: x['v'] if x['tipo'] == 'Entrada' else -x['v'], axis=1)
        df['Saldo'] = df['vs'].cumsum() + saldo_inicial
        st.line_chart(df.set_index('dt')['Saldo'], height=250)
    conn.close()

st.markdown('</div>', unsafe_allow_html=True)