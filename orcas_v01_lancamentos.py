import streamlit as st
import pandas as pd
from datetime import datetime

# Importando a ajuda do arquivo dedicado para Lançamentos
from orcas_v01_ajuda_lancamentos import renderizar_ajuda_lancamentos


def exibir_lancamentos(df, supabase, ID_USUARIO_LOGADO, d_ini_db, d_fim_db, s_db, format_moeda, ir_para_o_topo):
    """
    Sub-rotina da Tela Lançamentos - Integridade total da lógica de meses e saldos,
    com visualização expansível (>) para Cartões ($CCP/LCL) e Pagamentos Parciais.
    Ajuste estético: botão '>' colado à coluna Status e sem fundo azul.
    """

    if 'msg_sucesso' not in st.session_state: 
        st.session_state.msg_sucesso = False

    # Controle de expansão das linhas (Cartão ou Parciais)
    if 'exp_rows' not in st.session_state:
        st.session_state.exp_rows = {}

    # --- CABEÇALHO ALINHADO COM BOTÃO DE AJUDA ---
    col_titulo, col_ajuda = st.columns([4, 1])
    
    with col_titulo:
        st.markdown(f'<div class="titulo-tela" style="margin-top:0px;">Lançamentos: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
        
    with col_ajuda:
        st.markdown("""
            <style>
            /* Estilo do botão AJUDA */
            div.stButton > button[kind="primary"] {
                background-color: #007ba7 !important;
                color: white !important;
                border: none !important;
                height: 38px !important;
                font-size: 14px !important;
                font-weight: bold !important;
            }
            div.stButton > button[kind="primary"]:hover {
                background-color: #005f81 !important;
                color: white !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        if st.button("AJUDA", type="primary", use_container_width=True):
            st.session_state["exibir_ajuda_lancamentos"] = not st.session_state.get("exibir_ajuda_lancamentos", False)
            st.rerun()

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
            
            mes_fechado = mes_str < mes_hoje_str
            
            def calcular_total_tipo(df_tipo, e_fechado):
                total = 0
                if e_fechado:
                    itens_principais = df_tipo[(df_tipo['valor_plan'] > 0) | ((df_tipo['valor_plan'] == 0) & (df_tipo['valor_real'] > 0))]
                    for _, x in itens_principais.iterrows():
                        if x['permite_parcial']:
                            desc_pai = str(x['descricao']).strip().upper()
                            mask_filhos = (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_pai) & (df_mes['valor_plan'] == 0)
                            v_parciais = df_mes[mask_filhos]['parcial_real'].sum()
                            total += v_parciais
                        else:
                            if x['status'] == 'Realizado':
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
                    # --- CSS RESTAURADO E ESTILO DO BOTÃO DE EXPANSÃO (SEM AZUL E PROXIMO) ---
                    st.markdown("""
                        <style>
                        .tab-scroll { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 2px; }
                        .tab-body { min-width: 580px; display: flex; flex-direction: column; font-family: sans-serif; }
                        .tab-row { display: flex; flex-direction: row; align-items: center; padding: 6px 0; border-bottom: 1px solid #eee; }
                        .tab-hdr { font-weight: bold; background-color: #f8f9fa; border-top: 1px solid #ddd; }
                        .c-dt { width: 85px; font-size: 13px; flex-shrink: 0; }
                        .c-ds { width: 220px; font-size: 13px; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 5px; }
                        .c-es { width: 35px; font-size: 13px; flex-shrink: 0; text-align: center; }
                        .c-vl { width: 90px; font-size: 13px; flex-shrink: 0; text-align: right; }
                        .c-st { width: 55px; font-size: 12px; flex-shrink: 0; text-align: center; font-weight: bold; margin-left: 5px; }
                        
                        .linha-alerta-saida { color: #FF0000 !important; font-weight: bold; }
                        .linha-alerta-entrada { color: #0000FF !important; font-weight: bold; }

                        /* Estilo geral dos botões da tabela */
                        div.stButton > button:not([kind="primary"]) {
                            background-color: #1E3A8A !important;
                            color: #FFFFFF !important;
                            border: none !important;
                            border-radius: 4px !important;
                            font-size: 11px !important;
                            padding: 2px 6px !important;
                            height: 28px !important;
                            min-height: 28px !important;
                        }
                        div.stButton > button:not([kind="primary"]):hover {
                            background-color: #1E40AF !important;
                            color: #FFFFFF !important;
                        }

                        /* Estilo específico para o botão de expansão '>' (fundo transparente/sem azul) */
                        div.stButton > button[key*="btn_exp_"] {
                            background-color: transparent !important;
                            color: #333333 !important;
                            font-weight: bold !important;
                            font-size: 14px !important;
                            border: none !important;
                            box-shadow: none !important;
                            padding: 0px !important;
                        }
                        div.stButton > button[key*="btn_exp_"]:hover {
                            background-color: #e2e8f0 !important;
                            color: #000000 !important;
                        }
                        </style>
                    """, unsafe_allow_html=True)

                    eh_ccp_mask = df_mes['cc_tipo'].fillna('').astype(str).str.strip().str.upper().isin(['$CCP', 'CCP'])

                    df_exibir = df_mes[
                        ((df_mes['valor_plan'] > 0) | (df_mes['valor_real'] > 0) | eh_ccp_mask) &
                        (df_mes['cc_tipo'].fillna('').astype(str).str.strip().str.upper() != 'LCL')
                    ].sort_values('data')
                    
                    # Cabeçalho da tabela com proporção ajustada para colar o botão na coluna Status
                    c_hdr_linha, c_hdr_btn = st.columns([15, 1], vertical_alignment="center")
                    with c_hdr_linha:
                        h_hdr = '<div class="tab-scroll"><div class="tab-body">'
                        h_hdr += '<div class="tab-row tab-hdr"><div class="c-dt">Data</div><div class="c-ds">Descrição</div><div class="c-es">E/S</div><div class="c-vl">V.Plan</div><div class="c-vl">V.Real</div><div class="c-st">Status</div></div>'
                        h_hdr += '</div></div>'
                        st.markdown(h_hdr, unsafe_allow_html=True)

                    for idx, row in df_exibir.iterrows():
                        desc_row_upper = str(row['descricao']).strip().upper()
                        
                        v_ac = df_mes[
                            df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_row_upper
                        ]['parcial_real'].sum()
                        
                        v_re = v_ac if v_ac > 0 else row['valor_real']
                        eh_cartao_ccp = str(row.get('cc_tipo')).strip().upper() in ['$CCP', 'CCP']

                        # Busca LCLs vinculadas (Compras do cartão)
                        df_lcls_cartao = pd.DataFrame()
                        if eh_cartao_ccp:
                            df_lcls_cartao = df_mes[
                                (df_mes['cc_tipo'].fillna('').astype(str).str.strip().str.upper() == 'LCL') & 
                                (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_row_upper)
                            ]
                            v_re = df_lcls_cartao['valor_real'].sum()

                        dt_e = pd.to_datetime(row['data']).strftime('%d/%m/%Y')
                        st_e = 'PLAN' if row['status'] == 'Planejado' else 'REAL'
                        
                        classe_cor = ""
                        if v_re > row['valor_plan']:
                            if row['tipo'] == 'Saída':
                                classe_cor = " linha-alerta-saida"
                            elif row['tipo'] == 'Entrada':
                                classe_cor = " linha-alerta-entrada"
                        
                        # Identifica lançamentos de baixa parcial (filhos)
                        filhos_parciais = df_mes[
                            (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_row_upper) & 
                            (df_mes['valor_plan'] == 0) & 
                            (df_mes['parcial_real'] > 0)
                        ]

                        # Verifica se o item tem conteúdo expansível (Cartão com compras LCL ou Item com Parciais)
                        tem_subitens = (eh_cartao_ccp and not df_lcls_cartao.empty) or (not filhos_parciais.empty)
                        key_exp = f"exp_{mes_str}_{idx}_{row['id']}"
                        is_expanded = st.session_state.exp_rows.get(key_exp, False)

                        # Desenha a linha principal
                        h_row = '<div class="tab-scroll"><div class="tab-body">'
                        h_row += f'<div class="tab-row{classe_cor}">'
                        h_row += f'<div class="c-dt">{dt_e}</div><div class="c-ds">{row["descricao"]}</div><div class="c-es">{row["tipo"][0]}</div>'
                        h_row += f'<div class="c-vl">{format_moeda(row["valor_plan"])}</div><div class="c-vl">{format_moeda(v_re)}</div><div class="c-st">{st_e}</div>'
                        h_row += '</div>'

                        # Renderiza sub-itens expansíveis se estiver ativo (>)
                        if is_expanded:
                            # 1. Sub-itens do Cartão de Crédito (LCLs)
                            if eh_cartao_ccp and not df_lcls_cartao.empty:
                                for _, lcl in df_lcls_cartao.iterrows():
                                    desc_lcl = lcl.get('cc_descricao') if 'cc_descricao' in lcl and pd.notna(lcl['cc_descricao']) else lcl['descricao']
                                    dt_compra = lcl.get('cc_data_compra') if 'cc_data_compra' in lcl and pd.notna(lcl['cc_data_compra']) else lcl['data']
                                    dt_compra_str = pd.to_datetime(dt_compra).strftime('%d/%m/%Y')
                                    
                                    h_row += f'<div class="tab-row{classe_cor}" style="font-style: italic; opacity: 0.85; background-color: #f1f5f9;">'
                                    h_row += f'<div class="c-dt"></div><div class="c-ds" style="padding-left:15px;">> {desc_lcl} ({dt_compra_str})</div><div class="c-es">S</div>'
                                    h_row += f'<div class="c-vl">{format_moeda(lcl["valor_plan"])}</div><div class="c-vl">{format_moeda(lcl["valor_real"])}</div><div class="c-st">LCL</div>'
                                    h_row += f'</div>'
                            
                            # 2. Sub-itens de Parciais
                            if not filhos_parciais.empty:
                                for _, f in filhos_parciais.iterrows():
                                    dt_f = pd.to_datetime(f['parcial_data']).strftime('%d/%m/%Y')
                                    h_row += f'<div class="tab-row{classe_cor}" style="font-style: italic; opacity: 0.85; background-color: #f1f5f9;">'
                                    h_row += f'<div class="c-dt"></div><div class="c-ds" style="padding-left:15px;">> Parcial: {dt_f}</div><div class="c-es">{f["tipo"][0]}</div>'
                                    h_row += f'<div class="c-vl">---</div><div class="c-vl">{format_moeda(f["parcial_real"])}</div><div class="c-st">REAL</div>'
                                    h_row += f'</div>'

                        h_row += '</div></div>'

                        # Proporção ajustada para colar o botão à coluna Status (15:1)
                        c_linha, c_btn = st.columns([15, 1], vertical_alignment="center")
                        with c_linha:
                            st.markdown(h_row, unsafe_allow_html=True)
                        with c_btn:
                            if tem_subitens:
                                icon_btn = "v" if is_expanded else ">"
                                if st.button(icon_btn, key=f"btn_exp_{key_exp}"):
                                    st.session_state.exp_rows[key_exp] = not is_expanded
                                    st.rerun()
                else:
                    st.write("ℹ️ Nenhum lançamento para este mês.")
            
            saldo_acumulado_mes = saldo_final_mes

    if st.button("Voltar ao Topo", key="btn_topo_lanc"): 
        ir_para_o_topo()