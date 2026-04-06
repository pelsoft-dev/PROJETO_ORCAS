import streamlit as st
import pandas as pd
from datetime import datetime
import streamlit.components.v1 as components

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
                    # Construção do HTML com CSS embutido para garantir a linha única (no-wrap)
                    html_content = """
                    <style>
                        .tabela-wrapper { font-family: sans-serif; width: 100%; overflow-x: auto; white-space: nowrap; }
                        .linha { display: flex; border-bottom: 1px solid #eee; padding: 8px 0; align-items: center; min-width: 500px; }
                        .cabecalho { font-weight: bold; background: #f9f9f9; border-top: 1px solid #ddd; }
                        .c-data { width: 90px; font-size: 13px; }
                        .c-desc { width: 180px; font-size: 13px; overflow: hidden; text-overflow: ellipsis; padding: 0 5px; }
                        .c-es { width: 30px; font-size: 13px; text-align: center; }
                        .c-val { width: 85px; font-size: 13px; text-align: right; }
                        .c-st { width: 40px; font-size: 12px; text-align: center; font-weight: bold; margin-left: 10px; }
                    </style>
                    <div class="tabela-wrapper">
                        <div class="linha cabecalho">
                            <div class="c-data">Data</div><div class="c-desc">Descrição</div><div class="c-es">E/S</div>
                            <div class="c-val">V.Plan</div><div class="c-val">V.Real</div><div class="c-st">St</div>
                        </div>
                    """

                    df_exibir = df_mes[(df_mes['valor_plan'] > 0) | ((df_mes['valor_plan'] == 0) & (df_mes['valor_real'] > 0))].sort_values('data')
                    
                    for _, row in df_exibir.iterrows():
                        v_acum = df_mes[df_mes['descricao'] == row['descricao']]['parcial_real'].sum()
                        v_real_exibir = v_acum if v_acum > 0 else row['valor_real']
                        data_exibir = pd.to_datetime(row['data']).strftime('%d/%m/%Y')
                        
                        html_content += f"""
                        <div class="linha">
                            <div class="c-data">{data_exibir}</div>
                            <div class="c-desc">{row['descricao']}</div>
                            <div class="c-es">{row['tipo'][0]}</div>
                            <div class="c-val">{format_moeda(row['valor_plan'])}</div>
                            <div class="c-val">{format_moeda(v_real_exibir)}</div>
                            <div class="c-st">{'PL' if row['status'] == 'Planejado' else 'RL'}</div>
                        </div>
                        """

                        filhos = df_mes[(df_mes['descricao'] == row['descricao']) & (df_mes['valor_plan'] == 0) & (df_mes['parcial_real'] > 0)]
                        for _, filho in filhos.iterrows():
                            data_f = pd.to_datetime(filho['parcial_data']).strftime('%d/%m/%Y')
                            html_content += f"""
                            <div class="linha" style="color: gray;">
                                <div class="c-data"></div>
                                <div class="c-desc" style="padding-left:15px;">> {data_f}</div>
                                <div class="c-es">{filho['tipo'][0]}</div>
                                <div class="c-val">---</div>
                                <div class="c-val">{format_moeda(filho['parcial_real'])}</div>
                                <div class="c-st">RL</div>
                            </div>
                            """
                    
                    html_content += "</div>"
                    # Renderiza o HTML final garantindo que o Streamlit não trate como texto
                    st.markdown(html_content, unsafe_allow_html=True)
                else:
                    st.write("ℹ️ Nenhum lançamento para este mês.")
            
            saldo_acumulado_mes = saldo_final_mes

    if st.button("Voltar ao Topo", key="btn_topo_lanc"): 
        ir_para_o_topo()