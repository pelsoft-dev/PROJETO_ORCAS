import streamlit as st
import pandas as pd
from datetime import datetime

# Importando a ajuda do arquivo dedicado para Lançamentos
from orcas_v01_ajuda_lancamentos import renderizar_ajuda_lancamentos

# --- DIÁLOGO / MODAL VISÃO CARTÃO ---
@st.dialog("💳 Detalhamento do Cartão de Crédito")
def abrir_modal_visao_cartao(df_mes, descricao_cartao, mes_str, format_moeda):
    st.subheader(f"{descricao_cartao} — {datetime.strptime(mes_str, '%Y-%m').strftime('%m/%Y')}")
    
    # Filtra os lançamentos espelhos ($CCL) deste mês
    # Pode filtrar também por cartão específico se houver a coluna cartao_id
    if 'tipo_cc' in df_mes.columns:
        df_ccl = df_mes[df_mes['tipo_cc'] == '$CCL'].copy()
    else:
        df_ccl = pd.DataFrame()

    if not df_ccl.empty:
        st.markdown("**Itens/Despesas da Fatura:**")
        
        # Tabela formatada para os itens do cartão
        df_exibir = pd.DataFrame({
            "Data": pd.to_datetime(df_ccl['data']).dt.strftime('%d/%m/%Y'),
            "Descrição": df_ccl['descricao'],
            "Valor (R$)": df_ccl.apply(lambda r: format_moeda(r['valor_real'] if r['valor_real'] > 0 else r['valor_plan']), axis=1)
        })
        
        st.dataframe(df_exibir, use_container_width=True, hide_index=True)
        
        # Totalizador da Fatura
        total_fatura = df_ccl.apply(lambda r: r['valor_real'] if r['valor_real'] > 0 else r['valor_plan'], axis=1).sum()
        st.markdown(f"### **Total da Fatura: R$ {format_moeda(total_fatura)}**")
    else:
        st.info("Nenhum lançamento espelho ($CCL) encontrado para esta fatura neste mês.")

    if st.button("Fechar", use_container_width=True, type="primary"):
        st.rerun()


def exibir_lancamentos(df, supabase, ID_USUARIO_LOGADO, d_ini_db, d_fim_db, s_db, format_moeda, ir_para_o_topo):
    """
    Sub-rotina da Tela Lançamentos - Integridade total da lógica de meses e saldos.
    """
    # Verificação de segurança para evitar os erros de AttributeError
    if 'msg_sucesso' not in st.session_state: 
        st.session_state.msg_sucesso = False

    # --- CABEÇALHO ALINHADO COM BOTÃO DE AJUDA ---
    col_titulo, col_ajuda = st.columns([4, 1])
    
    with col_titulo:
        st.markdown(f'<div class="titulo-tela" style="margin-top:0px;">Lançamentos: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
        
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
            st.session_state["exibir_ajuda_lancamentos"] = not st.session_state.get("exibir_ajuda_lancamentos", False)
            st.rerun()

    # --- EXIBIÇÃO DA TELA DE AJUDA SE O BOTÃO FOR CLICADO ---
    if st.session_state.get("exibir_ajuda_lancamentos", False):
        renderizar_ajuda_lancamentos()

    if d_ini_db and d_fim_db:
        meses_periodo = []
        data_atual_loop = d_ini_db.replace(day=1)
        while data_atual_loop <= d_fim_db:
            meses_periodo.append(data_atual_loop.strftime('%Y-%m'))
            if data_atual_loop.month == 12: 
                data_atual_loop = data_atual_loop.replace(year=data_atual_loop.year + 1, month=1)
            else: 
                data_atual_loop = data_atual_loop.replace(month=data_atual_loop.month + 1)
        
        saldo_acumulado_mes = s_db
        mes_hoje_str = datetime.now().strftime('%Y-%m')
        
        for mes_str in meses_periodo:
            mask_mes = pd.to_datetime(df['data']).dt.strftime('%Y-%m') == mes_str
            df_mes = df[mask_mes].copy()
            
            # Identifica se é um mês já fechado (anterior ao mês corrente)
            mes_fechado = mes_str < mes_hoje_str
            
            def calcular_total_tipo(df_tipo, e_fechado):
                total = 0
                
                # REGRA DE OURO: Ignora lançamentos de Cartão ($CCP e $CCL) do total/cabeçalho
                if 'tipo_cc' in df_tipo.columns:
                    df_filtrado = df_tipo[~df_tipo['tipo_cc'].isin(['$CCP', '$CCL'])].copy()
                else:
                    df_filtrado = df_tipo.copy()

                if e_fechado:
                    # PARA MESES FECHADOS: Soma estritamente apenas os realizados
                    itens_principais = df_filtrado[(df_filtrado['valor_plan'] > 0) | ((df_filtrado['valor_plan'] == 0) & (df_filtrado['valor_real'] > 0))]
                    
                    for _, x in itens_principais.iterrows():
                        if x['permite_parcial']:
                            v_parciais = df_mes[(df_mes['descricao'] == x['descricao']) & (df_mes['valor_plan'] == 0)]['parcial_real'].sum()
                            total += v_parciais
                        else:
                            if x['status'] == 'Realizado':
                                total += x['valor_real']
                else:
                    # PARA MÊS CORRENTE E FUTUROS: Mantém lógica original de orçamento/projeção
                    itens_principais = df_filtrado[(df_filtrado['valor_plan'] > 0) | ((df_filtrado['valor_plan'] == 0) & (df_filtrado['valor_real'] > 0))]
                    for _, x in itens_principais.iterrows():
                        if x['permite_parcial']:
                            v_parciais = df_mes[(df_mes['descricao'] == x['descricao']) & (df_mes['valor_plan'] == 0)]['parcial_real'].sum()
                            total += max(x['valor_plan'], v_parciais)
                        else:
                            total += x['valor_real'] if x['valor_real'] > 0 else x['valor_plan']
                return total

            entradas_mes = calcular_total_tipo(df_mes[df_mes['tipo'] == 'Entrada'], mes_fechado)
            saidas_mes = calcular_total_tipo(df_mes[df_mes['tipo'] == 'Saída'], mes_fechado)
            saldo_final_mes = saldo_acumulado_mes + entradas_mes - saidas_mes
            nome_mes_exibicao = datetime.strptime(mes_str, '%Y-%m').strftime('%m/%Y')
            
            with st.expander(f"📅 {nome_mes_exibicao} | Saldo Final: R$ {format_moeda(saldo_final_mes)}"):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Saldo Inicial", f"R$ {format_moeda(saldo_acumulado_mes)}")
                col2.metric("Entradas (+)", f"R$ {format_moeda(entradas_mes)}")
                col3.metric("Saídas (-)", f"R$ {format_moeda(saidas_mes)}")
                col4.metric("Saldo Final", f"R$ {format_moeda(saldo_final_mes)}")
                st.divider()

                if not df_mes.empty:
                    st.markdown("""
                        <style>
                        .tab-scroll { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 10px; }
                        .tab-body { min-width: 600px; display: flex; flex-direction: column; font-family: sans-serif; }
                        .tab-row { display: flex; flex-direction: row; align-items: center; padding: 7px 0; border-bottom: 1px solid #eee; }
                        .tab-hdr { font-weight: bold; background-color: #f8f9fa; border-top: 1px solid #ddd; }
                        .c-dt { width: 85px; font-size: 13px; flex-shrink: 0; }
                        .c-ds { width: 220px; font-size: 13px; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 5px; }
                        .c-es { width: 35px; font-size: 13px; flex-shrink: 0; text-align: center; }
                        .c-vl { width: 90px; font-size: 13px; flex-shrink: 0; text-align: right; }
                        .c-st { width: 55px; font-size: 12px; flex-shrink: 0; text-align: center; font-weight: bold; margin-left: 5px; }
                        .c-bt { width: 110px; flex-shrink: 0; text-align: right; }
                        /* Classes de cor forçadas para garantir a exibição */
                        .linha-alerta-saida { color: #FF0000 !important; font-weight: bold; }
                        .linha-alerta-entrada { color: #0000FF !important; font-weight: bold; }
                        </style>
                    """, unsafe_allow_html=True)

                    # Filtramos itens espelhos ($CCL) da visão principal do mês
                    if 'tipo_cc' in df_mes.columns:
                        df_exibir = df_mes[(df_mes['tipo_cc'] != '$CCL') & ((df_mes['valor_plan'] > 0) | ((df_mes['valor_plan'] == 0) & (df_mes['valor_real'] > 0)))].sort_values('data')
                    else:
                        df_exibir = df_mes[(df_mes['valor_plan'] > 0) | ((df_mes['valor_plan'] == 0) & (df_mes['valor_real'] > 0))].sort_values('data')
                    
                    # Cabeçalho da Tabela
                    st.markdown("""
                        <div class="tab-scroll"><div class="tab-body">
                        <div class="tab-row tab-hdr">
                            <div class="c-dt">Data</div>
                            <div class="c-ds">Descrição</div>
                            <div class="c-es">E/S</div>
                            <div class="c-vl">V.Plan</div>
                            <div class="c-vl">V.Real</div>
                            <div class="c-st">Status</div>
                            <div class="c-bt">Ação</div>
                        </div>
                        </div></div>
                    """, unsafe_allow_html=True)
                    
                    for idx, row in df_exibir.iterrows():
                        v_ac = df_mes[df_mes['descricao'] == row['descricao']]['parcial_real'].sum()
                        v_re = v_ac if v_ac > 0 else row['valor_real']
                        dt_e = pd.to_datetime(row['data']).strftime('%d/%m/%Y')
                        st_e = 'PLAN' if row['status'] == 'Planejado' else 'REAL'
                        
                        # Definição da classe de cor
                        classe_cor = ""
                        if v_re > row['valor_plan']:
                            if row['tipo'] == 'Saída':
                                classe_cor = " linha-alerta-saida"
                            elif row['tipo'] == 'Entrada':
                                classe_cor = " linha-alerta-entrada"
                        
                        # Renderização usando colunas nativas do Streamlit para acoplamento do botão
                        col_r1, col_r2, col_r3, col_r4, col_r5, col_r6, col_r7 = st.columns([1.2, 3, 0.6, 1.5, 1.5, 0.8, 1.8])
                        
                        col_r1.write(f"**{dt_e}**" if classe_cor else dt_e)
                        col_r2.write(f"**{row['descricao']}**" if classe_cor else row['descricao'])
                        col_r3.write(row['tipo'][0])
                        col_r4.write(format_moeda(row["valor_plan"]))
                        col_r5.write(format_moeda(v_re))
                        col_r6.write(st_e)
                        
                        # Botão "Visão Cartão" na extrema direita para registros $CCP
                        is_ccp = ('tipo_cc' in row) and (row['tipo_cc'] == '$CCP')
                        if is_ccp:
                            if col_r7.button("💳 Visão Cartão", key=f"btn_cc_{row.get('id', idx)}"):
                                abrir_modal_visao_cartao(df_mes, row['descricao'], mes_str, format_moeda)
                        else:
                            col_r7.write("")

                        # Exibição dos filhos (parciais)
                        filhos = df_mes[(df_mes['descricao'] == row['descricao']) & (df_mes['valor_plan'] == 0) & (df_mes['parcial_real'] > 0)]
                        for _, f in filhos.iterrows():
                            dt_f = pd.to_datetime(f['parcial_data']).strftime('%d/%m/%Y')
                            col_f1, col_f2, col_f3, col_f4, col_f5, col_f6, col_f7 = st.columns([1.2, 3, 0.6, 1.5, 1.5, 0.8, 1.8])
                            col_f1.write("")
                            col_f2.write(f"↳ *{dt_f}*")
                            col_f3.write(f['tipo'][0])
                            col_f4.write("---")
                            col_f5.write(format_moeda(f['parcial_real']))
                            col_f6.write("REAL")
                            col_f7.write("")
                else:
                    st.write("ℹ️ Nenhum lançamento para este mês.")
            
            saldo_acumulado_mes = saldo_final_mes

    if st.button("Voltar ao Topo", key="btn_topo_lanc"): 
        ir_para_o_topo()