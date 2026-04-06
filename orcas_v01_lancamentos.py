import streamlit as st
import pandas as pd
from datetime import datetime

def exibir_lancamentos(df, supabase, ID_USUARIO_LOGADO, d_ini_db, d_fim_db, s_db, format_moeda, ir_para_o_topo):
    """
    Sub-rotina da Tela Lançamentos - Integridade total da lógica de meses e saldos.
    """
    st.markdown(f'<div class="titulo-tela">Lançamentos: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    # CSS AJUSTADO: Fixa larguras para garantir que tudo apareça no celular sem cortar
    st.markdown("""
        <style>
        .linha-compacta {
            display: flex;
            flex-direction: row;
            flex-wrap: nowrap;
            align-items: center;
            justify-content: flex-start;
            width: 100%;
            border-bottom: 1px solid #f0f2f6;
            padding: 4px 0;
        }
        /* Larguras calculadas para caber em ~360px (padrão celular) */
        .col-data { min-width: 75px; width: 75px; font-size: 0.75rem; }
        .col-desc { min-width: 100px; max-width: 120px; font-size: 0.75rem; flex-grow: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 4px; }
        .col-tipo { min-width: 25px; width: 25px; font-size: 0.75rem; text-align: center; }
        .col-valor { min-width: 65px; width: 65px; font-size: 0.75rem; text-align: right; }
        .col-status { min-width: 40px; width: 40px; font-size: 0.7rem; text-align: center; font-weight: bold; margin-left: 5px; }
        
        .header-compacto { font-weight: bold; background-color: #f8f9fa; border-top: 1px solid #e6e9ef; }
        </style>
    """, unsafe_allow_html=True)

    if d_ini_db and d_fim_db:
        # Loop de meses e saldo acumulado original (mantido integralmente)
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
            
            # Lógica de soma condicional para Entradas e Saídas
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
                # Métricas do topo
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Saldo Inicial", f"R$ {format_moeda(saldo_acumulado_mes)}")
                col2.metric("Entradas (+)", f"R$ {format_moeda(entradas_mes)}")
                col3.metric("Saídas (-)", f"R$ {format_moeda(saidas_mes)}")
                col4.metric("Saldo Final", f"R$ {format_moeda(saldo_final_mes)}")
                st.divider()

                if not df_mes.empty:
                    # Cabeçalho da Lista
                    st.markdown(f"""
                        <div class="linha-compacta header-compacto">
                            <div class="col-data">Data</div>
                            <div class="col-desc">Descrição</div>
                            <div class="col-tipo">E/S</div>
                            <div class="col-valor">V.Plan</div>
                            <div class="col-valor">V.Real</div>
                            <div class="col-status">St</div>
                        </div>
                    """, unsafe_allow_html=True)

                    # Itens Pais ou Diretos
                    df_exibir = df_mes[(df_mes['valor_plan'] > 0) | ((df_mes['valor_plan'] == 0) & (df_mes['valor_real'] > 0))].sort_values('data')
                    
                    for _, row in df_exibir.iterrows():
                        v_acum = df_mes[df_mes['descricao'] == row['descricao']]['parcial_real'].sum()
                        v_real_exibir = v_acum if v_acum > 0 else row['valor_real']
                        status_exibir = 'PL' if row['status'] == 'Planejado' else 'RL'
                        data_exibir = pd.to_datetime(row['data']).strftime('%d/%m/%Y')

                        st.markdown(f"""
                            <div class="linha-compacta">
                                <div class="col-data">{data_exibir}</div>
                                <div class="col-desc">{row['descricao']}</div>
                                <div class="col-tipo">{row['tipo'][0]}</div>
                                <div class="col-valor">{format_moeda(row['valor_plan'])}</div>
                                <div class="col-valor">{format_moeda(v_real_exibir)}</div>
                                <div class="col-status">{status_exibir}</div>
                            </div>
                        """, unsafe_allow_html=True)

                        # Associação de Filhos (parciais)
                        filhos = df_mes[(df_mes['descricao'] == row['descricao']) & (df_mes['valor_plan'] == 0) & (df_mes['parcial_real'] > 0)]
                        for _, filho in filhos.iterrows():
                            data_filho = pd.to_datetime(filho['parcial_data']).strftime('%d/%m/%Y')
                            st.markdown(f"""
                                <div class="linha-compacta" style="color: gray;">
                                    <div class="col-data"></div>
                                    <div class="col-desc" style="padding-left:10px;">> {data_filho}</div>
                                    <div class="col-tipo">{filho['tipo'][0]}</div>
                                    <div class="col-valor">---</div>
                                    <div class="col-valor">{format_moeda(filho['parcial_real'])}</div>
                                    <div class="col-status">RL</div>
                                </div>
                            """, unsafe_allow_html=True)
                else:
                    st.write("ℹ️ Nenhum lançamento para este mês.")
            
            saldo_acumulado_mes = saldo_final_mes

    if st.button("Voltar ao Topo", key="btn_topo_lanc"): 
        ir_para_o_topo()