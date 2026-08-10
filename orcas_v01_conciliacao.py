import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import calendar

from orcas_v01_ajuda_conciliacao import renderizar_ajuda_conciliacao

def calcular_vencimento_fatura(data_compra, dia_corte=15, dia_vencimento=20):
    """
    Calcula a data de vencimento da 1ª parcela de acordo com o dia de corte.
    Exemplo: Corte dia 15, Vencimento dia 20.
    - Compra até dia 15 -> Vence no dia 20 do MÊS ATUAL.
    - Compra após dia 15 -> Vence no dia 20 do MÊS SEGUINTE.
    """
    ano = data_compra.year
    mes = data_compra.month

    if data_compra.day > dia_corte:
        # Pula para o próximo mês
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1

    # Ajusta o dia de vencimento para o limite de dias do mês (ex: fev)
    dia_final = min(dia_vencimento, calendar.monthrange(ano, mes)[1])
    return datetime(ano, mes, dia_final).date()

def somar_meses_data(data_base, qtd_meses):
    """Avança N meses a partir de uma data mantendo coerência de dias."""
    ano = data_base.year + ((data_base.month + qtd_meses - 1) // 12)
    mes = ((data_base.month + qtd_meses - 1) % 12) + 1
    dia = min(data_base.day, calendar.monthrange(ano, mes)[1])
    return datetime(ano, mes, dia).date()

def exibir_conciliacao(df, supabase, ID_USUARIO_LOGADO, format_moeda, parse_moeda):
    """
    Sub-rotina da Tela Conciliação - Solução Estrita de Filtragem de Parciais e Cartão.
    """
    # --- CABEÇALHO ALINHADO COM BOTÃO DE AJUDA ---
    col_titulo, col_ajuda = st.columns([4, 1])
    
    with col_titulo:
        st.markdown(f'<div class="titulo-tela" style="margin-top:0px;">Conciliação: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
        
    with col_ajuda:
        st.markdown("""
            <style>
            div.stButton > button:first-child {
                background-color: #007ba7 !important;
                color: white !important;
                border: none !important;
            }
            div.stButton > button:first-child:hover {
                background-color: #005f81 !important;
                color: white !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        if st.button("AJUDA", type="primary", use_container_width=True):
            st.session_state["exibir_ajuda_conciliacao"] = not st.session_state.get("exibir_ajuda_conciliacao", False)
            st.rerun()

    if st.session_state.get("exibir_ajuda_conciliacao", False):
        renderizar_ajuda_conciliacao()

    st.markdown("""
        <style>
        .block-container { padding-top: 2rem !important; }
        [data-testid="stWidgetLabel"] p { font-size: 0.85rem !important; white-space: nowrap !important; }
        .stMarkdown div p { margin-bottom: 0px !important; }
        hr { margin-top: 0.5rem !important; margin-bottom: 0.5rem !important; }
        </style>
    """, unsafe_allow_html=True)

    hoje_c = datetime.now().date()
    ini_mes_c = hoje_c.replace(day=1)
    limite_c = hoje_c - timedelta(days=4)

    col_aviso, col_tog = st.columns([4, 3])
    col_aviso.markdown('<div style="font-size: 0.8rem; color: #555; margin-top: 10px;">📱🔄 SE USANDO O CELULAR, TRABALHE COM ELE NA HORIZONTAL</div>', unsafe_allow_html=True)
    
    abrir_sem_plan = col_tog.toggle("Lançar sem Planejamento", value=st.session_state.get('abrir_sem_plan', False))
    st.session_state.abrir_sem_plan = abrir_sem_plan
    
    listar_todos_mes = col_tog.toggle("Listar todos Lançamentos do mês", value=st.session_state.get('listar_todos_mes', False))
    st.session_state.listar_todos_mes = listar_todos_mes
    
    st.divider()

    # --- ÁREA: LANÇAR SEM PLANEJAMENTO ---
    if st.session_state.abrir_sem_plan:
        cols_sp = st.columns([2.0, 0.8, 1.0, 1.2, 0.6, 0.5])
        sp_desc = cols_sp[0].text_input("Descrição", key="sp_desc", placeholder="Ex: Sapato")
        sp_tipo = cols_sp[1].selectbox("E/S", ["Saída", "Entrada"], key="sp_tipo")
        sp_valor = cols_sp[2].text_input("Valor Real", key="sp_valor", value="0,00")
        sp_cartao = cols_sp[3].text_input("Cartão (Opcional)", key="sp_cartao", placeholder="Ex: Itaú Master")
        sp_parc = cols_sp[4].number_input("Parc.", min_value=1, max_value=12, value=1, step=1, key="sp_parc")
        
        with cols_sp[5]:
            st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
            btn_confirmar = st.button("Ok", key="btn_sp_conf", use_container_width=True)
        
        if btn_confirmar:
            v_sp = parse_moeda(sp_valor)
            if sp_desc and v_sp > 0:
                is_cc = bool(sp_cartao.strip())
                qtd_p = int(sp_parc) if is_cc else 0

                # 1. LANÇAMENTO ORIGINAL (LOU)
                # Recebe $CCL para ser neutralizado do total do mês se for feito no cartão
                supabase.table("lancamentos").insert({
                    "projeto_id": str(st.session_state.projeto_ativo),
                    "usuario_id": str(ID_USUARIO_LOGADO),
                    "descricao": sp_desc,
                    "data": hoje_c.strftime('%Y-%m-%d'),
                    "data_vencimento": hoje_c.strftime('%Y-%m-%d'),
                    "tipo": sp_tipo,
                    "valor_plan": 0, 
                    "valor_real": v_sp,
                    "status": "Realizado", 
                    "parcial_real": 0, 
                    "permite_parcial": False,
                    "cc_tipo": "$CCL" if is_cc else None,
                    "cc_qtd_parcelas": qtd_p
                }).execute()

                # 2. LANÇAMENTOS DO CARTÃO DE CRÉDITO (LCL)
                if is_cc:
                    v_parcela = round(v_sp / (qtd_p if qtd_p > 0 else 1), 2)
                    dt_primeiro_venc = calcular_vencimento_fatura(hoje_c, dia_corte=15, dia_vencimento=20)

                    for i in range(max(1, qtd_p)):
                        dt_venc_parc = somar_meses_data(dt_primeiro_venc, i)
                        supabase.table("lancamentos").insert({
                            "projeto_id": str(st.session_state.projeto_ativo),
                            "usuario_id": str(ID_USUARIO_LOGADO),
                            "descricao": f"{sp_desc} ({i+1}/{qtd_p}) - {sp_cartao.strip()}",
                            "data": dt_venc_parc.strftime('%Y-%m-%d'),
                            "data_vencimento": dt_venc_parc.strftime('%Y-%m-%d'),
                            "tipo": "Saída",
                            "valor_plan": 0,
                            "valor_real": v_parcela,
                            "status": "Realizado",
                            "cc_tipo": None,  # Este LCL É considerado no total do mês
                            "cc_qtd_parcelas": 0
                        }).execute()

                st.session_state.abrir_sem_plan = False
                st.rerun()
        st.divider()

    df_c = df.copy()
    if not df_c.empty:
        df_c['dt_obj'] = pd.to_datetime(df_c['data']).dt.date
        df_c['parcial_real'] = pd.to_numeric(df_c['parcial_real'], errors='coerce').fillna(0)
        
        # 🟢 REGRA CRÍTICA: SEPARA TOTALMENTE OS REGISTROS DE PARCIAL DA LISTA PRINCIPAL
        df_base_tela = df_c[df_c['parcial_real'] == 0].copy()
        
        if st.session_state.listar_todos_mes:
            proximo_mes = (ini_mes_c + timedelta(days=32)).replace(day=1)
            fim_mes_c = proximo_mes - timedelta(days=1)
            df_f = df_base_tela[(df_base_tela['dt_obj'] >= ini_mes_c) & (df_base_tela['dt_obj'] <= fim_mes_c)].copy()
        else:
            df_f = df_base_tela[
                (df_base_tela['dt_obj'] >= ini_mes_c) & 
                (df_base_tela['dt_obj'] <= hoje_c) & 
                (
                    (df_base_tela['status'].isin(['Planejado', 'PLAN'])) | 
                    ((df_base_tela['status'].isin(['Realizado', 'REAL'])) & (df_base_tela['dt_obj'] >= limite_c)) | 
                    ((df_base_tela['valor_plan'] == 0) & (df_base_tela['valor_real'] > 0))
                )
            ].copy()
        
        parciais_topo = df_f[(df_f['permite_parcial'] == True) & (df_f['dt_obj'] >= ini_mes_c)]
        demais_itens = df_f[~df_f.index.isin(parciais_topo.index)].sort_values('dt_obj', ascending=False)
        df_final_concilia = pd.concat([parciais_topo, demais_itens])

        # CABEÇALHO DA TABELA
        h1, h2, h3, h4, h5, h6 = st.columns([2.2, 0.5, 1.1, 1.1, 1.1, 0.5])
        h1.write("**Data - Descrição**")
        h2.write("**E/S**")
        h3.write("**V. Plan.**")
        h4.write("**V. Real**")
        h5.write("**Valor Parcial**")
        h6.write("**Ação**")
        st.divider()

        for _, row in df_final_concilia.iterrows():
            # Soma todas as parciais diretamente no DataFrame 'df' original
            v_acumulado_desc = df[df['descricao'] == row['descricao']]['parcial_real'].fillna(0).sum()
            cor_txt = "red" if (row['valor_plan'] > 0 and v_acumulado_desc > row['valor_plan']) else "black"
            
            st.markdown('<div style="margin-bottom: -32px;"></div>', unsafe_allow_html=True)
            
            c1, c2, c3, c4, c5, c6 = st.columns([2.2, 0.5, 1.1, 1.1, 1.1, 0.5])
            
            c1.markdown(f"<span style='color:{cor_txt}; font-weight: 500;'>{row['dt_obj'].strftime('%d/%m/%Y')} - {row['descricao']}</span>", unsafe_allow_html=True)
            cor_tipo = 'red' if row['tipo'] == 'Saída' else 'blue'
            c2.markdown(f"<span style='color:{cor_tipo}'>{row['tipo'][0]}</span>", unsafe_allow_html=True)
            
            if row['permite_parcial']:
                c3.markdown(f"<span style='color:{cor_txt}'>{format_moeda(row['valor_plan'])}</span>", unsafe_allow_html=True)
                c4.markdown(f"<span style='color:{cor_txt}'>{format_moeda(v_acumulado_desc)}</span>", unsafe_allow_html=True)
                
                v_key = f"v_p_{row['id']}"
                if v_key not in st.session_state: 
                    st.session_state[v_key] = 0
                
                v_parc_in = c5.text_input("", key=f"p_{row['id']}_{st.session_state[v_key]}", value="0,00", label_visibility="collapsed")
                
                if c6.button("Ok", key=f"btn_p_{row['id']}", use_container_width=True):
                    v_dig = parse_moeda(v_parc_in)
                    if v_dig > 0:
                        # Grava o LPR (Lançamento Parcial)
                        supabase.table("lancamentos").insert({
                            "projeto_id": str(st.session_state.projeto_ativo),
                            "usuario_id": str(ID_USUARIO_LOGADO), 
                            "descricao": row['descricao'], 
                            "data": ini_mes_c.strftime('%Y-%m-%d'), 
                            "data_vencimento": ini_mes_c.strftime('%Y-%m-%d'), 
                            "tipo": row['tipo'],
                            "valor_plan": 0, 
                            "valor_real": 0, 
                            "status": "Planejado",
                            "parcial_real": v_dig, 
                            "parcial_data": hoje_c.strftime('%Y-%m-%d'), 
                            "permite_parcial": False
                        }).execute()
                        st.session_state[v_key] += 1
                        st.rerun()
            else:
                c3.write(format_moeda(row['valor_plan']))
                if row['status'] in ['Realizado', 'REAL']:
                    c4.write(format_moeda(row['valor_real']))
                    c6.write("✅")
                else:
                    v_norm_in = c4.text_input("", key=f"n_{row['id']}", value="0,00", label_visibility="collapsed")
                    if c6.button("Ok", key=f"btn_n_{row['id']}", use_container_width=True):
                        v_para_gravar = parse_moeda(v_norm_in)
                        if v_para_gravar == 0: 
                            v_para_gravar = row['valor_plan']
                        
                        supabase.table("lancamentos").update({
                            "valor_real": v_para_gravar, 
                            "status": "Realizado"
                        }).eq("id", row['id']).execute()
                        st.rerun()
            st.divider()
    else:
        st.info("Nenhum lançamento pendente para conciliação.")