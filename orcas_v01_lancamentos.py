import streamlit as st
import pandas as pd
from datetime import datetime

# Importando a ajuda do arquivo dedicado para Lançamentos
from orcas_v01_ajuda_lancamentos import renderizar_ajuda_lancamentos


def exibir_lancamentos(df, supabase, ID_USUARIO_LOGADO, d_ini_db, d_fim_db, s_db, format_moeda, ir_para_o_topo):
    """
    Sub-rotina da Tela Lançamentos.
    Exibe LCLs mestre/avulsos na listagem sem duplicar saldos.
    """

    if 'msg_sucesso' not in st.session_state: 
        st.session_state.msg_sucesso = False

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

    # --- GARANTIA CONTRA KEYERROR EM NOVOS PLANOS ---
    if 'cc_tipo' not in df.columns: df['cc_tipo'] = ''
    if 'permite_parcial' not in df.columns: df['permite_parcial'] = False
    if 'parcial_real' not in df.columns: df['parcial_real'] = 0.0
    if 'status' not in df.columns: df['status'] = 'Planejado'
    if 'cc_descricao' not in df.columns: df['cc_descricao'] = ''

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
                
                # IGNORA LCLs planejados para não somar 2x com a fatura mestre
                s_cc = df_tipo.get('cc_tipo', pd.Series('', index=df_tipo.index)).fillna('').astype(str).str.strip().str.upper()
                df_tipo_filtrado = df_tipo[s_cc != 'LCL']
                
                if e_fechado:
                    itens_principais = df_tipo_filtrado[(df_tipo_filtrado['valor_plan'] > 0) | ((df_tipo_filtrado['valor_plan'] == 0) & (df_tipo_filtrado['valor_real'] > 0))]
                    for _, x in itens_principais.iterrows():
                        if x.get('permite_parcial', False):
                            desc_pai = str(x['descricao']).strip().upper()
                            mask_filhos = (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_pai) & (df_mes['valor_plan'] == 0)
                            v_parciais = df_mes[mask_filhos].get('parcial_real', pd.Series(0)).sum()
                            total += v_parciais
                        else:
                            if x.get('status') == 'Realizado':
                                if str(x.get('cc_tipo', '')).strip().upper() in ['$CCP', 'CCP']:
                                    desc_cc = str(x['descricao']).strip().upper()
                                    m_lcl = (df_mes.get('cc_tipo', pd.Series('')).fillna('').astype(str).str.strip().str.upper() == 'LCL')
                                    m_desc = (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_cc) | (df_mes.get('cc_descricao', pd.Series('')).fillna('').astype(str).str.strip().str.upper() == desc_cc)
                                    soma_lcls = df_mes[m_lcl & m_desc]['valor_real'].sum()
                                    total += soma_lcls
                                else:
                                    total += x['valor_real']
                else:
                    itens_principais = df_tipo_filtrado[(df_tipo_filtrado['valor_plan'] > 0) | ((df_tipo_filtrado['valor_plan'] == 0) & (df_tipo_filtrado['valor_real'] > 0))]
                    for _, x in itens_principais.iterrows():
                        if x.get('permite_parcial', False):
                            desc_pai = str(x['descricao']).strip().upper()
                            mask_filhos = (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_pai) & (df_mes['valor_plan'] == 0)
                            v_parciais = df_mes[mask_filhos].get('parcial_real', pd.Series(0)).sum()
                            total += max(x['valor_plan'], v_parciais)
                        else:
                            if str(x.get('cc_tipo', '')).strip().upper() in ['$CCP', 'CCP']:
                                desc_cc = str(x['descricao']).strip().upper()
                                m_lcl = (df_mes.get('cc_tipo', pd.Series('')).fillna('').astype(str).str.strip().str.upper() == 'LCL')
                                m_desc = (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_cc) | (df_mes.get('cc_descricao', pd.Series('')).fillna('').astype(str).str.strip().str.upper() == desc_cc)
                                soma_lcls_real = df_mes[m_lcl & m_desc]['valor_real'].sum()
                                soma_lcls_plan = df_mes[m_lcl & m_desc]['valor_plan'].sum()
                                val_cartao = soma_lcls_real if soma_lcls_real > 0 else (soma_lcls_plan if soma_lcls_plan > 0 else x['valor_plan'])
                                total += val_cartao
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
                    # --- CSS REVISADO COM CLASSE EXCLUSIVA det-linha ---
                    st.markdown("""
                        <style>
                        .tab-scroll { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 2px; }
                        .tab-body { width: fit-content; min-width: 580px; display: flex; flex-direction: column; font-family: sans-serif; }
                        .tab-row { display: flex; flex-direction: row; align-items: center; padding: 6px 0; border-bottom: 1px solid #eee; }
                        .tab-hdr { font-weight: bold; background-color: #f8f9fa; border-top: 1px solid #ddd; }
                        .c-dt { width: 85px; font-size: 13px; flex-shrink: 0; }
                        .c-ds { width: 220px; font-size: 13px; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 5px; }
                        .c-es { width: 35px; font-size: 13px; flex-shrink: 0; text-align: center; }
                        .c-vl { width: 90px; font-size: 13px; flex-shrink: 0; text-align: right; }
                        .c-st { width: 55px; font-size: 12px; flex-shrink: 0; text-align: center; font-weight: bold; margin-left: 5px; }
                        
                        /* Margem de 38px à direita do Status */
                        .c-act { width: 40px; margin-left: 38px; flex-shrink: 0; display: flex; align-items: center; justify-content: flex-start; }

                        .linha-alerta-saida { color: #FF0000 !important; font-weight: bold; }
                        .linha-alerta-entrada { color: #0000FF !important; font-weight: bold; }

                        /* Oculta seta nativa apenas das nossas linhas */
                        details.det-linha > summary {
                            list-style: none !important;
                            outline: none !important;
                            cursor: pointer;
                        }
                        details.det-linha > summary::-webkit-details-marker,
                        details.det-linha > summary::marker {
                            display: none !important;
                        }

                        /* Estilo da caixa do botão */
                        .btn-exp-native {
                            background-color: transparent !important;
                            color: #000000 !important;
                            border: 1.5px solid #222222 !important;
                            border-radius: 6px !important;
                            font-size: 11px !important;
                            font-weight: bold !important;
                            padding: 1px 5px !important;
                            height: 22px !important;
                            min-width: 28px !important;
                            display: inline-flex !important;
                            align-items: center !important;
                            justify-content: center !important;
                            user-select: none !important;
                        }
                        .btn-exp-native:hover {
                            background-color: #e5e7eb !important;
                            border-color: #000000 !important;
                        }

                        /* 1. ESTADO FECHADO (PADRÃO): Mostra >> e esconde ^^ */
                        details.det-linha > summary .lbl-closed { display: inline !important; }
                        details.det-linha > summary .lbl-open { display: none !important; }

                        /* 2. ESTADO ABERTO DA PRÓPRIA LINHA: Esconde >> e mostra ^^ */
                        details.det-linha[open] > summary .lbl-closed { display: none !important; }
                        details.det-linha[open] > summary .lbl-open { display: inline !important; }

                        /* Outros botões padrão do Streamlit */
                        div.stButton > button:not([kind="primary"]) {
                            background-color: #1E3A8A !important;
                            color: #FFFFFF !important;
                            border: none !important;
                            border-radius: 4px !important;
                            font-size: 11px !important;
                            padding: 2px 6px !important;
                            height: 28px !important;
                        }
                        </style>
                    """, unsafe_allow_html=True)

                    s_cc_m = df_mes.get('cc_tipo', pd.Series('', index=df_mes.index)).fillna('').astype(str).str.strip().str.upper()
                    eh_ccp_mask = s_cc_m.isin(['$CCP', 'CCP'])

                    # --- CORREÇÃO DA DUPLICAÇÃO ---
                    # Para a linha PRINCIPAL: Exibe apenas itens com valor_plan > 0 ou cartões CCP mestres.
                    # As baixas parciais (valor_plan == 0 com parcial_real > 0) não entram aqui como linhas principais, 
                    # apenas dentro do expansor (filhos_parciais).
                    mask_item_principal = (df_mes['valor_plan'] > 0) | eh_ccp_mask
                    
                    # Oculta LCLs planejados da lista principal
                    v_parcial_series = df_mes.get('parcial_real', pd.Series(0, index=df_mes.index)).fillna(0)
                    mask_exibir_item = (s_cc_m != 'LCL') | ((s_cc_m == 'LCL') & ((df_mes['valor_real'] > 0) | (v_parcial_series > 0)))

                    df_exibir = df_mes[mask_item_principal & mask_exibir_item].sort_values('data')
                    
                    # Cabeçalho da tabela
                    h_hdr = '<div class="tab-scroll"><div class="tab-body">'
                    h_hdr += '<div class="tab-row tab-hdr"><div class="c-dt">Data</div><div class="c-ds">Descrição</div><div class="c-es">E/S</div><div class="c-vl">V.Plan</div><div class="c-vl">V.Real</div><div class="c-st">Status</div><div class="c-act"></div></div>'

                    for idx, row in df_exibir.iterrows():
                        desc_row_upper = str(row['descricao']).strip().upper()
                        
                        v_ac = df_mes[
                            df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_row_upper
                        ].get('parcial_real', pd.Series(0)).sum()
                        
                        v_plan = row['valor_plan']
                        v_re = v_ac if v_ac > 0 else row['valor_real']
                        eh_cartao_ccp = str(row.get('cc_tipo', '')).strip().upper() in ['$CCP', 'CCP']

                        # Busca LCLs vinculadas ao cartão mestre (por descricao ou cc_descricao)
                        df_lcls_cartao = pd.DataFrame()
                        if eh_cartao_ccp:
                            mask_lcl = (df_mes.get('cc_tipo', pd.Series('')).fillna('').astype(str).str.strip().str.upper() == 'LCL')
                            mask_desc_dir = (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_row_upper)
                            mask_desc_cc = (df_mes.get('cc_descricao', pd.Series('')).fillna('').astype(str).str.strip().str.upper() == desc_row_upper)
                            df_lcls_cartao = df_mes[mask_lcl & (mask_desc_dir | mask_desc_cc)]
                            
                            if not df_lcls_cartao.empty:
                                v_plan = df_lcls_cartao['valor_plan'].sum()
                                v_re = df_lcls_cartao['valor_real'].sum()

                        dt_e = pd.to_datetime(row['data']).strftime('%d/%m/%Y')
                        st_e = 'PLAN' if row.get('status') == 'Planejado' else 'REAL'
                        
                        classe_cor = ""
                        if v_re > v_plan:
                            if row['tipo'] == 'Saída':
                                classe_cor = " linha-alerta-saida"
                            elif row['tipo'] == 'Entrada':
                                classe_cor = " linha-alerta-entrada"
                        
                        # Identifica lançamentos de baixa parcial (filhos)
                        filhos_parciais = df_mes[
                            (df_mes['descricao'].fillna('').astype(str).str.strip().str.upper() == desc_row_upper) & 
                            (df_mes['valor_plan'] == 0) & 
                            (df_mes.get('parcial_real', pd.Series(0)) > 0)
                        ]

                        tem_subitens = (eh_cartao_ccp and not df_lcls_cartao.empty) or (not filhos_parciais.empty)

                        # Montagem do bloco de linha
                        if tem_subitens:
                            h_hdr += f'<details class="det-linha"><summary>'
                            h_hdr += f'<div class="tab-row{classe_cor}">'
                            h_hdr += f'<div class="c-dt">{dt_e}</div><div class="c-ds">{row["descricao"]}</div><div class="c-es">{row["tipo"][0]}</div>'
                            h_hdr += f'<div class="c-vl">{format_moeda(v_plan)}</div><div class="c-vl">{format_moeda(v_re)}</div><div class="c-st">{st_e}</div>'
                            h_hdr += f'<div class="c-act"><span class="btn-exp-native"><span class="lbl-closed">&gt;&gt;</span><span class="lbl-open">^^</span></span></div>'
                            h_hdr += '</div></summary>'

                            # Subitens exibidos quando aberto
                            # 1. Compras no Cartão de Crédito
                            if eh_cartao_ccp and not df_lcls_cartao.empty:
                                for _, lcl in df_lcls_cartao.iterrows():
                                    desc_cc_val = str(lcl.get('cc_descricao', '')).strip()
                                    desc_lcl = desc_cc_val if desc_cc_val and desc_cc_val.upper() != desc_row_upper else lcl['descricao']
                                    
                                    dt_compra = lcl.get('cc_data_compra') if 'cc_data_compra' in lcl and pd.notna(lcl['cc_data_compra']) else lcl['data']
                                    dt_compra_str = pd.to_datetime(dt_compra).strftime('%d/%m/%Y')
                                    
                                    h_hdr += f'<div class="tab-row{classe_cor}" style="font-style: italic; opacity: 0.85; background-color: #f1f5f9;">'
                                    h_hdr += f'<div class="c-dt"></div><div class="c-ds" style="padding-left:15px;">> {desc_lcl} ({dt_compra_str})</div><div class="c-es">S</div>'
                                    h_hdr += f'<div class="c-vl">{format_moeda(lcl["valor_plan"])}</div><div class="c-vl">{format_moeda(lcl["valor_real"])}</div><div class="c-st">PLAN</div><div class="c-act"></div>'
                                    h_hdr += f'</div>'
                            
                            # 2. Parciais
                            if not filhos_parciais.empty:
                                for _, f in filhos_parciais.iterrows():
                                    dt_f = pd.to_datetime(f['parcial_data']).strftime('%d/%m/%Y')
                                    h_hdr += f'<div class="tab-row{classe_cor}" style="font-style: italic; opacity: 0.85; background-color: #f1f5f9;">'
                                    h_hdr += f'<div class="c-dt"></div><div class="c-ds" style="padding-left:15px;">> Parcial: {dt_f}</div><div class="c-es">{f["tipo"][0]}</div>'
                                    h_hdr += f'<div class="c-vl">---</div><div class="c-vl">{format_moeda(f["parcial_real"])}</div><div class="c-st">REAL</div><div class="c-act"></div>'
                                    h_hdr += f'</div>'

                            h_hdr += '</details>'
                        else:
                            # Linha normal sem subitens
                            h_hdr += f'<div class="tab-row{classe_cor}">'
                            h_hdr += f'<div class="c-dt">{dt_e}</div><div class="c-ds">{row["descricao"]}</div><div class="c-es">{row["tipo"][0]}</div>'
                            h_hdr += f'<div class="c-vl">{format_moeda(v_plan)}</div><div class="c-vl">{format_moeda(v_re)}</div><div class="c-st">{st_e}</div>'
                            h_hdr += f'<div class="c-act"></div>'
                            h_hdr += '</div>'

                    h_hdr += '</div></div>'
                    st.markdown(h_hdr, unsafe_allow_html=True)
                else:
                    st.write("ℹ️ Nenhum lançamento para este mês.")
            
            saldo_acumulado_mes = saldo_final_mes

    if st.button("Voltar ao Topo", key="btn_topo_lanc"): 
        ir_para_o_topo()