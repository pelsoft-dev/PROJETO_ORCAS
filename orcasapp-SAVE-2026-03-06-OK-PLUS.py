import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÃO E ESTILO (LOGO COM BALEIA E ESTABILIDADE) ---
st.set_page_config(page_title="Orcas Pro", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    .stDeployButton {display:none;}
    footer {visibility: hidden;}
    
    /* PONTO 1: Logo com Baleia e Fonte Ajustada */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        padding-top: 1rem !important; 
    }
    .logo-container {
        display: flex;
        align-items: center;
        margin-top: -15px;
        margin-bottom: 0px;
    }
    .logo-sidebar {
        font-size: 2.8rem !important; /* Diminuída para caber a baleia ao lado */
        font-weight: bold;
        color: #1E3A8A;
        font-family: 'Arial Black', sans-serif;
        margin-left: 10px;
    }
    .baleia-icon {
        font-size: 2.5rem;
    }
    .espacador-custom {
        height: 20px; 
    }
    
    /* Largura dos botões */
    div[data-testid="column"] button {
        width: 100% !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. FUNÇÕES DE SUPORTE ---
def format_moeda(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def parse_moeda(texto):
    try:
        return float(str(texto).replace('.', '').replace(',', '.'))
    except:
        return 0.0

def init_db():
    conn = sqlite3.connect('orcas.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS lancamentos 
                  (id INTEGER PRIMARY KEY, data TEXT, descricao TEXT, 
                   valor_plan REAL, valor_real REAL, tipo TEXT, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 3. SIDEBAR (LOGO E MENU) ---
if 'd_mestre_ini' not in st.session_state:
    st.session_state.d_mestre_ini = datetime.now().date()
if 'd_mestre_fim' not in st.session_state:
    st.session_state.d_mestre_fim = (datetime.now() + timedelta(days=90)).date()

with st.sidebar:
    # PONTO 1: Baleia ao lado esquerdo do ORCAS
    st.markdown('''
        <div class="logo-container">
            <span class="baleia-icon">🐋</span>
            <span class="logo-sidebar">ORCAS</span>
        </div>
    ''', unsafe_allow_html=True)
    
    st.markdown('<div class="espacador-custom"></div>', unsafe_allow_html=True)
    
    s_ini_txt = st.text_input("Saldo Inicial (R$)", value="0,00")
    saldo_inicial = parse_moeda(s_ini_txt)
    
    st.markdown('<div class="espacador-custom"></div>', unsafe_allow_html=True)
    
    escolha = st.radio("Menu", ["🏠 Dashboard", "📅 Projetar", "✅ Conciliação", "⚙️ Gestão"], label_visibility="collapsed")

hoje = datetime.now().date()

# --- 4. TELAS ---

if escolha == "⚙️ Gestão":
    st.subheader("Configurações do Fluxo")
    col_g1, col_g2 = st.columns(2)
    st.session_state.d_mestre_ini = col_g1.date_input("Início do Fluxo", value=st.session_state.d_mestre_ini, format="DD/MM/YYYY")
    st.session_state.d_mestre_fim = col_g2.date_input("Término do Fluxo", value=st.session_state.d_mestre_fim, format="DD/MM/YYYY")

elif escolha == "🏠 Dashboard":
    conn = sqlite3.connect('orcas.db')
    df = pd.read_sql_query("SELECT * FROM lancamentos WHERE data BETWEEN ? AND ? ORDER BY data ASC", 
                           conn, params=(st.session_state.d_mestre_ini.strftime('%Y-%m-%d'), st.session_state.d_mestre_fim.strftime('%Y-%m-%d')))
    conn.close()

    if not df.empty:
        df['data_dt'] = pd.to_datetime(df['data'])
        df['v'] = df.apply(lambda x: x['valor_real'] if x['valor_real'] > 0 else x['valor_plan'], axis=1)
        df['v_sinal'] = df.apply(lambda x: x['v'] if x['tipo'] == 'Entrada' else -x['v'], axis=1)
        df['Saldo_Acum'] = df['v_sinal'].cumsum() + saldo_inicial
        
        st.line_chart(df.set_index('data_dt')['Saldo_Acum'], height=250)
        
        df['Mes_Ano'] = df['data_dt'].dt.strftime('%Y-%m')
        saldo_transitado = saldo_inicial
        
        for mes_ref in sorted(df['Mes_Ano'].unique()):
            with st.expander(f"📅 {datetime.strptime(mes_ref, '%Y-%m').strftime('%m/%Y')}", expanded=True):
                m_df = df[df['Mes_Ano'] == mes_ref].copy()
                m_df['Data'] = m_df['data_dt'].dt.strftime('%d/%m/%Y')
                m_df['Planejado'] = m_df['valor_plan'].apply(format_moeda)
                m_df['Realizado'] = m_df['valor_real'].apply(format_moeda)
                st.table(m_df[['Data', 'descricao', 'tipo', 'Planejado', 'Realizado']])
                
                ent, sai = m_df[m_df['tipo'] == 'Entrada']['v'].sum(), m_df[m_df['tipo'] == 'Saída']['v'].sum()
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Anterior", format_moeda(saldo_transitado))
                c2.metric("Entradas", format_moeda(ent))
                c3.metric("Saídas", format_moeda(sai))
                saldo_final_mes = saldo_transitado + (ent - sai)
                c4.metric("Saldo Final", format_moeda(saldo_final_mes))
                saldo_transitado = saldo_final_mes

elif escolha == "📅 Projetar":
    col1, col2, col3 = st.columns(3)
    with col1:
        desc = st.text_input("Descrição", key="p_desc")
        v_txt = st.text_input("Valor", value="0,00", key="p_val")
        tipo = st.selectbox("E/S", ["Entrada", "Saída"], key="p_tipo")
    with col2:
        dia_mes = st.text_input("Dia do Mês (1-31 ou *)", key="p_dia_m")
        dia_sem = st.selectbox("Dia da Semana", ["", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"], key="p_dia_s")
        dia_esp = st.date_input("Dia Específico", value=None, format="DD/MM/YYYY", key="p_dia_e")
    with col3:
        d_ini = st.date_input("Início", value=st.session_state.d_mestre_ini, format="DD/MM/YYYY", key="p_ini")
        d_fim = st.date_input("Até", value=st.session_state.d_mestre_fim, format="DD/MM/YYYY", key="p_fim")
        regra_fds = st.radio("Fim de Semana", ["Manter", "Antecipa", "Posterga"], horizontal=True, key="p_fds")
    
    bloqueado = d_fim > st.session_state.d_mestre_fim
    if bloqueado: st.error(f"⚠️ Limite da Gestão: {st.session_state.d_mestre_fim.strftime('%d/%m/%Y')}")

    c_b1, c_b2, c_res = st.columns([0.8, 0.8, 4])
    
    if c_b1.button("Incluir", disabled=bloqueado):
        valor = parse_moeda(v_txt)
        conn = sqlite3.connect('orcas.db')
        curr = d_ini
        cont = 0
        dias_map = {"Segunda": "Monday", "Terça": "Tuesday", "Quarta": "Wednesday", "Quinta": "Thursday", "Sexta": "Friday", "Sábado": "Saturday", "Domingo": "Sunday"}
        while curr <= d_fim:
            match = (dia_esp and curr == dia_esp) or (dia_mes == "*") or (dia_mes and str(curr.day) == dia_mes) or (dia_sem != "" and curr.strftime('%A') == dias_map.get(dia_sem, ""))
            if match:
                dt_f = curr.strftime('%Y-%m-%d')
                conn.execute("INSERT INTO lancamentos (data, descricao, valor_plan, valor_real, tipo, status) VALUES (?,?,?,?,?,?)", (dt_f, desc, valor, 0.0, tipo, 'Planejado'))
                cont += 1
            curr += timedelta(days=1)
        conn.commit(); conn.close()
        st.session_state.msg = f"✅ {cont} lançamentos incluídos!"
        st.rerun()
        
    if c_b2.button("Excluir"):
        conn = sqlite3.connect('orcas.db')
        cursor = conn.execute("DELETE FROM lancamentos WHERE descricao = ? AND tipo = ? AND data BETWEEN ? AND ?", (desc, tipo, d_ini.strftime('%Y-%m-%d'), d_fim.strftime('%Y-%m-%d')))
        cont = cursor.rowcount
        conn.commit(); conn.close()
        st.session_state.msg = f"🗑️ {cont} lançamentos excluídos!"
        st.rerun()

    if 'msg' in st.session_state:
        c_res.info(st.session_state.msg)
        del st.session_state.msg

elif escolha == "✅ Conciliação":
    # PONTO 3: Revertido layout (sem bolinhas) e ordem decrescente
    conn = sqlite3.connect('orcas.db')
    df_c = pd.read_sql_query("""
        SELECT * FROM lancamentos 
        WHERE data <= ? 
        AND data BETWEEN ? AND ?
        ORDER BY data DESC
    """, conn, params=(hoje.strftime('%Y-%m-%d'), st.session_state.d_mestre_ini.strftime('%Y-%m-%d'), st.session_state.d_mestre_fim.strftime('%Y-%m-%d')))
    conn.close()

    if not df_c.empty:
        c_h = st.columns([1, 2.5, 0.4, 0.8, 0.8, 0.5])
        headers = ["Data", "Descrição", "E/S", "Plan", "Real", "V"]
        for col, lab in zip(c_h, headers): col.write(f"**{lab}**")

        for i, row in df_c.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([1, 2.5, 0.4, 0.8, 0.8, 0.5])
            dt_exib = datetime.strptime(row['data'], '%Y-%m-%d').strftime('%d/%m/%Y')
            
            c1.text(dt_exib)
            c2.text(row['descricao'])
            c3.text(row['tipo'][0])
            c4.text(format_moeda(row['valor_plan']))
            
            # PONTO 4: Edição de valor com Enter e Botão de Confirmação Corrigido
            val_input = c5.text_input("", value=format_moeda(row['valor_real']), key=f"r_{row['id']}", label_visibility="collapsed")
            novo_val = parse_moeda(val_input)
            
            if novo_val != row['valor_real'] and novo_val != 0:
                conn = sqlite3.connect('orcas.db')
                conn.execute("UPDATE lancamentos SET valor_real = ?, status = 'Realizado' WHERE id = ?", (novo_val, row['id']))
                conn.commit(); conn.close()
                st.rerun()

            # O botão agora força o rerun para garantir que o Dashboard e a tabela atualizem na hora
            if c6.button("✔️", key=f"b_{row['id']}"):
                conn = sqlite3.connect('orcas.db')
                conn.execute("UPDATE lancamentos SET valor_real = valor_plan, status = 'Realizado' WHERE id = ?", (row['id'],))
                conn.commit(); conn.close()
                st.rerun()
    else:
        st.info("Nenhum lançamento encontrado para o período.")