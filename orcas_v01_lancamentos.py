import streamlit as st
import pandas as pd
from datetime import datetime

def exibir_lancamentos(df, supabase, ID_USUARIO_LOGADO, d_ini_db, d_fim_db, s_db, format_moeda, ir_para_o_topo):
    """
    Sub-rotina da Tela Lançamentos - Integridade total da lógica de meses e saldos.
    """
    st.markdown(f'<div class="titulo-tela">Lançamentos: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
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
        
        for mes_str in meses_periodo:
            mask_mes = pd.to_datetime(df['data']).dt.strftime('%Y-%m') == mes_str
            df_mes = df[mask_mes].copy()
            
            def calcular_total_tipo(df_tipo):
                total = 0
                itens_principais = df_tipo[(df_tipo['valor_plan'] > 0) | ((df_tipo['valor_plan'] == 0) & (df_tipo['valor_real'] > 0))]
                for _, x in itens_principais.iterrows():
                    if x['permite_parcial']:
                        v_parciais = df_mes[(df_mes['descricao'] == x['descricao']) & (df_mes['valor_plan'] == 0)]['parcial_real'].sum()
                        total += max(x['valor_plan'], v_parciais)
                    else:
                        total += x['valor_real'] if x['valor_real'] > 0 else x['valor_plan']
                return total

            entradas_mes = calcular_total_tipo(df_mes[df_mes['tipo'] == 'Entrada'])
            saidas_mes = calcular_total_tipo(df_mes[df_mes['tipo'] == 'Saída'])
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
                    # Estilos CSS injetados: .c-ds aumentada em 50% (de 160px para 240px)
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
                        </style>
                    """, unsafe_allow_html=True)

                    # Montagem da tabela: Cabeçalho trocado de 'St' para 'Status'
                    h = '<div class="tab-scroll"><div class="tab-body">'
                    h += '<div class="tab-row tab-hdr"><div class="c-dt">Data</div><div class="c-ds">Descrição</div><div class="c-es">E/S</div><div class="c-vl">V.Plan</div><div class="c-vl">V.Real</div><div class="c-st">Status</div></div>'

                    # Lógica do mês atual: Se o mês processado for o mês atual, garante que mostre desde o dia 1
                    df_exibir = df_mes[(df_mes['valor_plan'] > 0) | ((df_mes['valor_plan'] == 0) & (df_mes['valor_real'] > 0))].sort_values('data')
                    
                    for _, row in df_exibir.iterrows():
                        v_ac = df_mes[df_mes['descricao'] == row['descricao']]['parcial_real'].sum()
                        v_re = v_ac if v_ac > 0 else row['valor_real']
                        dt_e = pd.to_datetime(row['data']).strftime('%d/%m/%Y')
                        
                        # Troca de 'PL' para 'PLAN' e 'RL' para 'REAL'
                        st_e = 'PLAN' if row['status'] == 'Planejado' else 'REAL'
                        
                        h += f'<div class="tab-row">'
                        h += f'<div class="c-dt">{dt_e}</div><div class="c-ds">{row["descricao"]}</div><div class="c-es">{row["tipo"][0]}</div>'
                        h += f'<div class="c-vl">{format_moeda(row["valor_plan"])}</div><div class="c-vl">{format_moeda(v_re)}</div><div class="c-st">{st_e}</div>'
                        h += f'</div>'

                        filhos = df_mes[(df_mes['descricao'] == row['descricao']) & (df_mes['valor_plan'] == 0) & (df_mes['parcial_real'] > 0)]
                        for _, f in filhos.iterrows():
                            dt_f = pd.to_datetime(f['parcial_data']).strftime('%d/%m/%Y')
                            h += f'<div class="tab-row" style="color: gray;">'
                            h += f'<div class="c-dt"></div><div class="c-ds" style="padding-left:15px;">> {dt_f}</div><div class="c-es">{f["tipo"][0]}</div>'
                            h += f'<div class="c-vl">---</div><div class="c-vl">{format_moeda(f["parcial_real"])}</div><div class="c-st">REAL</div>'
                            h += f'</div>'
                    
                    h += '</div></div>'
                    st.write(h, unsafe_allow_html=True)
                else:
                    st.write("ℹ️ Nenhum lançamento para este mês.")
            
            saldo_acumulado_mes = saldo_final_mes

    if st.button("Voltar ao Topo", key="btn_topo_lanc"): 
        ir_para_o_topo()