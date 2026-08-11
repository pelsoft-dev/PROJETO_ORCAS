import streamlit as st
import pandas as pd
from datetime import datetime

# Importando a ajuda do arquivo dedicado para Lançamentos
from orcas_v01_ajuda_lancamentos import renderizar_ajuda_lancamentos

# --- MODAL / JANELA VISÃO CARTÃO ---
@st.dialog("Visão Cartão - Detalhamento das Faturas")
def abrir_visao_cartao(desc_cartao, df_mes_cartao, format_moeda):
    st.subheader(f"💳 {desc_cartao}")
    
    # Filtra os lançamentos LCL vinculados a este cartão no mês
    mask_lcls = (
        (df_mes_cartao['cc_tipo'].fillna('').astype(str).str.strip().str.upper() == 'LCL') &
        (df_mes_cartao['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_cartao.upper())
    )
    df_lcls = df_mes_cartao[mask_lcls].copy()
    
    if not df_lcls.empty:
        # Tabela formatada dos lançamentos LCL
        df_exibir_modal = pd.DataFrame({
            'Descrição': df_lcls['cc_descricao'],
            'Data': pd.to_datetime(df_lcls['data']).dt.strftime('%d/%m/%Y'),
            'Valor (R$)': df_lcls['valor_real'].apply(lambda v: format_moeda(v))
        })
        st.dataframe(df_exibir_modal, use_container_width=True, hide_index=True)
        
        total_fatura = df_lcls['valor_real'].sum()
        st.markdown(f"**Total da Fatura:** R$ {format_moeda(total_fatura)}")
    else:
        st.info("Nenhum lançamento (LCL) encontrado para este cartão neste mês.")


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
                if e_fechado:
                    # PARA MESES FECHADOS: Soma estritamente apenas os realizados
                    itens_principais = df_tipo[(df_tipo['valor_plan'] > 0) | ((df_tipo['valor_plan'] == 0) & (df_tipo['valor_real'] > 0))]
                    
                    for _, x in itens_principais.iterrows():
                        if x['permite_parcial']:
                            # Comparação insensível a case para filhas/parciais
                            desc_pai = str(x['descricao']).strip().upper()
                            mask_filhos = (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_pai) & (df_mes['valor_plan'] == 0)
                            v_parciais = df_mes[mask_filhos]['parcial_real'].sum()
                            total += v_parciais
                        else:
                            if x['status'] == 'Realizado':
                                # Se for cartão CCP, considera a soma de LCLs
                                if str(x.get('cc_tipo')).strip().upper() in ['$CCP', 'CCP']:
                                    desc_cc = str(x['descricao']).strip().upper()
                                    soma_lcls = df_mes[
                                        (df_mes['cc_tipo'].fillna('').astype(str).str.strip().str.upper() == 'LCL') & 
                                        (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_cc)
                                    ]['valor_real'].sum()
                                    total += soma_lcls
                                else:
                                    total += x['valor_real']
                else:
                    # PARA MÊS CORRENTE E FUTUROS: Mantém lógica original de orçamento/projeção
                    itens_principais = df_tipo[(df_tipo['valor_plan'] > 0) | ((df_tipo['valor_plan'] == 0) & (df_tipo['valor_real'] > 0))]
                    for _, x in itens_principais.iterrows():
                        if x['permite_parcial']:
                            desc_pai = str(x['descricao']).strip().upper()
                            mask_filhos = (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_pai) & (df_mes['valor_plan'] == 0)
                            v_parciais = df_mes[mask_filhos]['parcial_real'].sum()
                            total += max(x['valor_plan'], v_parciais)
                        else:
                            if str(x.get('cc_tipo')).strip().upper() in ['$CCP', 'CCP']:
                                desc_cc = str(x['descricao']).strip().upper()
                                soma_lcls = df_mes[
                                    (df_mes['cc_tipo'].fillna('').astype(str).str.strip().str.upper() == 'LCL') & 
                                    (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_cc)
                                ]['valor_real'].sum()
                                total += soma_lcls if soma_lcls > 0 else x['valor_plan']
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
                        .c-ds { width: 240px; font-size: 13px; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 5px; }
                        .c-es { width: 35px; font-size: 13px; flex-shrink: 0; text-align: center; }
                        .c-vl { width: 90px; font-size: 13px; flex-shrink: 0; text-align: right; }
                        .c-st { width: 55px; font-size: 12px; flex-shrink: 0; text-align: center; font-weight: bold; margin-left: 5px; }
                        /* Classes de cor forçadas para garantir a exibição */
                        .linha-alerta-saida { color: #FF0000 !important; font-weight: bold; }
                        .linha-alerta-entrada { color: #0000FF !important; font-weight: bold; }
                        </style>
                    """, unsafe_allow_html=True)

                    # Oculta da lista principal os lançamentos que são LCL
                    df_exibir = df_mes[
                        ((df_mes['valor_plan'] > 0) | ((df_mes['valor_plan'] == 0) & (df_mes['valor_real'] > 0))) &
                        (df_mes['cc_tipo'].fillna('').astype(str).str.strip().str.upper() != 'LCL')
                    ].sort_values('data')
                    
                    # Cabeçalho da tabela HTML
                    h_hdr = '<div class="tab-scroll"><div class="tab-body">'
                    h_hdr += '<div class="tab-row tab-hdr"><div class="c-dt">Data</div><div class="c-ds">Descrição</div><div class="c-es">E/S</div><div class="c-vl">V.Plan</div><div class="c-vl">V.Real</div><div class="c-st">Status</div></div>'
                    h_hdr += '</div></div>'
                    st.write(h_hdr, unsafe_allow_html=True)

                    for idx, row in df_exibir.iterrows():
                        desc_row_upper = str(row['descricao']).strip().upper()
                        
                        # Busca acumulado de parciais (caso exista)
                        v_ac = df_mes[
                            df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_row_upper
                        ]['parcial_real'].sum()
                        
                        v_re = v_ac if v_ac > 0 else row['valor_real']
                        eh_cartao_ccp = str(row.get('cc_tipo')).strip().upper() in ['$CCP', 'CCP']

                        # Se for um Cartão Pai ($CCP), o V.Real é a soma de todos os lançamentos LCL vinculados
                        if eh_cartao_ccp:
                            soma_lcls = df_mes[
                                (df_mes['cc_tipo'].fillna('').astype(str).str.strip().str.upper() == 'LCL') & 
                                (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_row_upper)
                            ]['valor_real'].sum()
                            v_re = soma_lcls

                        dt_e = pd.to_datetime(row['data']).strftime('%d/%m/%Y')
                        st_e = 'PLAN' if row['status'] == 'Planejado' else 'REAL'
                        
                        # Definição da classe de cor
                        classe_cor = ""
                        if v_re > row['valor_plan']:
                            if row['tipo'] == 'Saída':
                                classe_cor = " linha-alerta-saida"
                            elif row['tipo'] == 'Entrada':
                                classe_cor = " linha-alerta-entrada"
                        
                        h_row = '<div class="tab-scroll"><div class="tab-body">'
                        h_row += f'<div class="tab-row{classe_cor}">'
                        h_row += f'<div class="c-dt">{dt_e}</div><div class="c-ds">{row["descricao"]}</div><div class="c-es">{row["tipo"][0]}</div>'
                        h_row += f'<div class="c-vl">{format_moeda(row["valor_plan"])}</div><div class="c-vl">{format_moeda(v_re)}</div><div class="c-st">{st_e}</div>'
                        h_row += f'</div>'

                        # Busca por filhos/parciais
                        filhos = df_mes[
                            (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_row_upper) & 
                            (df_mes['valor_plan'] == 0) & 
                            (df_mes['parcial_real'] > 0)
                        ]
                        for _, f in filhos.iterrows():
                            dt_f = pd.to_datetime(f['parcial_data']).strftime('%d/%m/%Y')
                            h_row += f'<div class="tab-row{classe_cor}" style="font-style: italic; opacity: 0.8;">'
                            h_row += f'<div class="c-dt"></div><div class="c-ds" style="padding-left:15px;">> {dt_f}</div><div class="c-es">{f["tipo"][0]}</div>'
                            h_row += f'<div class="c-vl">---</div><div class="c-vl">{format_moeda(f["parcial_real"])}</div><div class="c-st">REAL</div>'
                            h_row += f'</div>'
                    
                        h_row += '</div></div>'
                        
                        if eh_cartao_ccp:
                            c_linha, c_btn = st.columns([5, 1])
                            with c_linha:
                                st.write(h_row, unsafe_allow_html=True)
                            with c_btn:
                                if st.button("Visão Cartão", key=f"btn_vc_{mes_str}_{idx}"):
                                    abrir_visao_cartao(str(row['descricao']), df_mes, format_moeda)
                        else:
                            st.write(h_row, unsafe_allow_html=True)
                else:
                    st.write("ℹ️ Nenhum lançamento para este mês.")
            
            saldo_acumulado_mes = saldo_final_mes

    if st.button("Voltar ao Topo", key="btn_topo_lanc"): 
        ir_para_o_topo()