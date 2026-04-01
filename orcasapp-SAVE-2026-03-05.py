import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÃO E CSS ---
st.set_page_config(page_title="Orcas Pro", layout="wide")

st.markdown("""
    <style>
    .block-container { padding-top: 0.5rem !important; }
    header { visibility: hidden !important; height: 0px; }
    footer { visibility: hidden !important; }
    input[type=number]::-webkit-inner-spin-button, 
    input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
    .stTextInput, .stDateInput, .stSelectbox { margin-bottom: -5px !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. BANCO DE DADOS ---
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

# --- 3. CABEÇALHO ---
st.write("### 🐋 Orcas Pro")
c_saldo, _ = st.columns([1, 4])
with c_saldo:
    s_ini_txt = st.text_input("Saldo Inicial:", value="0.00")
    try: saldo_inicial = float(s_ini_txt.replace(',', '.'))
    except: saldo_inicial = 0.0

tab1, tab2, tab3, tab4 = st.tabs(["🏠 Dashboard", "📅 Projetar / Excluir", "✅ Conciliação", "⚙️ Gestão"])

# --- 4. GESTÃO (DEFINIR PERÍODO MESTRE) ---
with tab4:
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        d_mestre_ini = st.date_input("Início do Fluxo", value=datetime.now(), format="DD/MM/YYYY")
    with col_g2:
        d_mestre_fim = st.date_input("Término do Fluxo", value=datetime.now() + timedelta(days=90), format="DD/MM/YYYY")

# --- 5. DASHBOARD (TODOS OS DIAS) ---
with tab1:
    conn = sqlite3.connect('orcas.db')
    df_raw = pd.read_sql_query("SELECT * FROM lancamentos", conn)
    conn.close()

    # Criação do calendário base
    datas_full = pd.date_range(start=d_mestre_ini, end=d_mestre_fim)
    df_calendario = pd.DataFrame({'data_dt': datas_full})
    df_calendario['data_str'] = df_calendario['data_dt'].dt.strftime('%Y-%m-%d')

    if not df_raw.empty:
        # Merge para garantir que todos os dias apareçam
        df_merge = pd.merge(df_calendario, df_raw, left_on='data_str', right_on='data', how='left')
        df_merge = df_merge.fillna({'valor_plan':0, 'valor_real':0, 'descricao': '-', 'tipo': 'N/A'})
    else:
        df_merge = df_calendario.copy()
        df_merge['valor_plan'] = 0.0
        df_merge['valor_real'] = 0.0
        df_merge['descricao'] = '-'
        df_merge['tipo'] = 'N/A'

    # Cálculos de Saldo
    df_merge['v'] = df_merge.apply(lambda x: x['valor_real'] if x['valor_real'] > 0 else x['valor_plan'], axis=1)
    df_merge['v_sinal'] = df_merge.apply(lambda x: x['v'] if x['tipo'] == 'Entrada' else (-x['v'] if x['tipo'] == 'Saída' else 0), axis=1)
    df_merge['Saldo_Acum'] = df_merge['v_sinal'].cumsum() + saldo_inicial
    
    st.line_chart(df_merge.set_index('data_dt')['Saldo_Acum'], height=150)
    
    df_merge['Mes_Ano'] = df_merge['data_dt'].dt.strftime('%Y-%m')
    saldo_transitado = saldo_inicial
    for mes_ref in sorted(df_merge['Mes_Ano'].unique()):
        with st.expander(f"📅 {datetime.strptime(mes_ref, '%Y-%m').strftime('%m/%Y')}", expanded=True):
            m_df = df_merge[df_merge['Mes_Ano'] == mes_ref].copy()
            m_df['Data_BR'] = m_df['data_dt'].dt.strftime('%d/%m/%Y')
            
            # Tabela compacta
            st.dataframe(m_df[['Data_BR', 'descricao', 'tipo', 'valor_plan', 'valor_real']], use_container_width=True, hide_index=True)
            
            ent = m_df[m_df['tipo'] == 'Entrada']['v'].sum()
            sai = m_df[m_df['tipo'] == 'Saída']['v'].sum()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Anterior", f"R$ {saldo_transitado:,.2f}")
            c2.metric("Entradas", f"R$ {ent:,.2f}")
            c3.metric("Saídas", f"R$ {sai:,.2f}")
            saldo_final_mes = saldo_transitado + (ent - sai)
            c4.metric("Saldo Final", f"R$ {saldo_final_mes:,.2f}")
            saldo_transitado = saldo_final_mes

# --- 6. PROJETAR / EXCLUIR ---
with tab2:
    with st.form("form_projetar_excluir"):
        col1, col2, col3 = st.columns(3)
        with col1:
            desc = st.text_input("Descrição")
            v_txt = st.text_input("Valor", value="0.00")
            tipo = st.selectbox("E/S", ["Entrada", "Saída"])
        with col2:
            dia_mes = st.text_input("Dia do Mês (1-31 ou *)")
            dia_sem = st.text_input("Dia da Semana")
            dia_esp = st.date_input("Dia Específico", value=None, format="DD/MM/YYYY")
        with col3:
            d_ini = st.date_input("Data de Início", value=d_mestre_ini, format="DD/MM/YYYY")
            d_fim = st.date_input("Data de Término", value=d_mestre_fim, format="DD/MM/YYYY")
            regra_fds = st.radio("Fim de Semana", ["Manter", "Antecipa", "Posterga"], horizontal=True)
        
        c_btn1, c_btn2, c_msg = st.columns([1, 1, 3])
        btn_incluir = c_btn1.form_submit_button("Incluir")
        btn_excluir = c_btn2.form_submit_button("Excluir")
        
        if btn_incluir or btn_excluir:
            try: valor = float(v_txt.replace(',', '.'))
            except: valor = 0.0
            
            conn = sqlite3.connect('orcas.db')
            curr = d_ini
            cont = 0
            while curr <= d_fim:
                match = False
                if dia_esp and curr == dia_esp: match = True
                elif dia_mes == "*": match = True
                elif dia_mes and str(curr.day) == dia_mes: match = True
                elif dia_sem and dia_sem.lower() in curr.strftime('%A').lower(): match = True
                
                if match:
                    dt_final = ajustar_fds(curr, regra_fds).strftime('%Y-%m-%d')
                    if btn_incluir:
                        conn.execute("INSERT INTO lancamentos (data, descricao, valor_plan, valor_real, tipo, status) VALUES (?,?,?,?,?,?)",
                                      (dt_final, desc, valor, 0.0, tipo, 'Planejado'))
                    elif btn_excluir:
                        conn.execute("DELETE FROM lancamentos WHERE data = ? AND descricao = ? AND tipo = ?", (dt_final, desc, tipo))
                    cont += 1
                curr += timedelta(days=1)
            conn.commit()
            conn.close()
            acao = "Incluído(s)" if btn_incluir else "Excluído(s)"
            c_msg.success(f"Sucesso: {cont} lançamento(s) {acao}!")

# --- 7. CONCILIAÇÃO (LISTA TUDO) ---
with tab3:
    conn = sqlite3.connect('orcas.db')
    df_db = pd.read_sql_query("SELECT * FROM lancamentos", conn)
    conn.close()
    
    # Criar lista completa de dias para conciliação
    datas_conc = pd.date_range(start=d_mestre_ini, end=d_mestre_fim)
    df_base_c = pd.DataFrame({'data_dt': datas_conc})
    df_base_c['data_str'] = df_base_c['data_dt'].dt.strftime('%Y-%m-%d')
    
    if not df_db.empty:
        df_final_c = pd.merge(df_base_c, df_db, left_on='data_str', right_on='data', how='left')
    else:
        df_final_c = df_base_c.copy()
        df_final_c[['valor_plan', 'valor_real', 'descricao', 'tipo']] = [0.0, 0.0, '-', 'N/A']

    df_final_c = df_final_c.fillna({'valor_plan':0, 'valor_real':0, 'descricao': '-', 'tipo': 'N/A'})

    cols = st.columns([1, 2, 0.5, 1, 1, 0.4])
    for col, h in zip(cols, ["Data", "Descrição", "E/S", "Plan", "Real", "V"]): col.write(f"**{h}**")

    for i, row in df_final_c.iterrows():
        # Pula apenas linhas que não tem lançamento algum
        if row['descricao'] == '-' and row['valor_plan'] == 0: continue
        
        c1, c2, c3, c4, c5, c6 = st.columns([1, 2, 0.5, 1, 1, 0.4])
        dt_exib = row['data_dt'].strftime('%d/%m/%Y')
        
        c1.text(dt_exib)
        c2.text(row['descricao'])
        c3.text(row['tipo'][0])
        c4.text(f"{row['valor_plan']:.2f}")
        
        # Valor Realizado
        val_real_input = c5.text_input("", value=str(row['valor_real']), key=f"inp_{i}_{row['id']}", label_visibility="collapsed")
        
        # Botão Check
        if c6.button("✔️", key=f"btn_{i}_{row['id']}"):
            conn_up = sqlite3.connect('orcas.db')
            conn_up.execute("UPDATE lancamentos SET valor_real = ?, status = 'Realizado' WHERE id = ?", (row['valor_plan'], row['id']))
            conn_up.commit()
            conn_up.close()
            st.rerun()