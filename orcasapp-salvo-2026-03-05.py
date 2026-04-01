# --- TELA: LANÇAMENTOS ---
elif escolha == "📑 Lançamentos":
    st.markdown(f'<div class="titulo-tela">Lançamentos: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    if d_ini_db and d_fim_db:
        # Loop de meses e saldo acumulado original (83+ linhas mantidas)
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
            
            # ACERTO CABEÇALHO: Lógica de soma condicional para Entradas e Saídas
            def calcular_total_tipo(df_tipo):
                total = 0
                # ACERTO: Considera itens planejados OU itens diretos (plan=0 e real>0)
                itens_principais = df_tipo[(df_tipo['valor_plan'] > 0) | ((df_tipo['valor_plan'] == 0) & (df_tipo['valor_real'] > 0))]
                
                for _, x in itens_principais.iterrows():
                    if x['permite_parcial']:
                        # Mantém a lógica: maior entre planejado e soma das parciais
                        v_parciais = df_mes[(df_mes['descricao'] == x['descricao']) & (df_mes['valor_plan'] == 0)]['parcial_real'].sum()
                        total += max(x['valor_plan'], v_parciais)
                    else:
                        # ACERTO: Se valor realizado > 0, usa ele, senão usa o planejado
                        total += x['valor_real'] if x['valor_real'] > 0 else x['valor_plan']
                return total

            entradas_mes = calcular_total_tipo(df_mes[df_mes['tipo'] == 'Entrada'])
            saidas_mes = calcular_total_tipo(df_mes[df_mes['tipo'] == 'Saída'])
                
            saldo_final_mes = saldo_acumulado_mes + entradas_mes - saidas_mes
            nome_mes_exibicao = datetime.strptime(mes_str, '%Y-%m').strftime('%m/%Y')
            
            with st.expander(f"📅 {nome_mes_exibicao} | Saldo Final: R$ {format_moeda(saldo_final_mes)}"):
                # Métricas do topo (originais)
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Saldo Inicial", f"R$ {format_moeda(saldo_acumulado_mes)}")
                col2.metric("Entradas (+)", f"R$ {format_moeda(entradas_mes)}")
                col3.metric("Saídas (-)", f"R$ {format_moeda(saidas_mes)}")
                col4.metric("Saldo Final", f"R$ {format_moeda(saldo_final_mes)}")
                st.divider()

                if not df_mes.empty:
                    # Cabeçalho da Lista
                    h1, h2, h3, h4, h5, h6 = st.columns([1.2, 3, 0.5, 1.2, 1.2, 0.8])
                    h1.write("**Data**"); h2.write("**Descrição**"); h3.write("**E/S**")
                    h4.write("**V. Plan**"); h5.write("**V. Real**"); h6.write("**Status**")

                    # ACERTO: Itens Pais ou Diretos (valor_plan > 0 OU (plan=0 e real>0))
                    df_exibir = df_mes[(df_mes['valor_plan'] > 0) | ((df_mes['valor_plan'] == 0) & (df_mes['valor_real'] > 0))].sort_values('data')
                    
                    for _, row in df_exibir.iterrows():
                        c1, c2, c3, c4, c5, c6 = st.columns([1.2, 3, 0.5, 1.2, 1.2, 0.8])
                        c1.write(pd.to_datetime(row['data']).strftime('%d/%m/%Y'))
                        c2.write(row['descricao'])
                        c3.write(row['tipo'][0])
                        c4.write(format_moeda(row['valor_plan']))
                        
                        v_acum = df_mes[df_mes['descricao'] == row['descricao']]['parcial_real'].sum()
                        c5.write(format_moeda(v_acum if v_acum > 0 else row['valor_real']))
                        c6.write('PLAN' if row['status'] == 'Planejado' else 'REAL')

                        # ASSOCIAÇÃO POR TEXTO (Filhos: valor_plan == 0 e parcial_real > 0)
                        filhos = df_mes[(df_mes['descricao'] == row['descricao']) & (df_mes['valor_plan'] == 0) & (df_mes['parcial_real'] > 0)]
                        for _, filho in filhos.iterrows():
                            f1, f2, f3, f4, f5, f6 = st.columns([1.2, 3, 0.5, 1.2, 1.2, 0.8])
                            # ACERTO: Retorno do formato DD/MM/AAAA (4 dígitos no ano)
                            f2.markdown(f"<span style='color:gray; padding-left:20px;'> >>> {pd.to_datetime(filho['parcial_data']).strftime('%d/%m/%Y')}</span>", unsafe_allow_html=True)
                            f3.markdown(f"<span style='color:gray;'>{filho['tipo'][0]}</span>", unsafe_allow_html=True)
                            f5.markdown(f"<span style='color:gray;'>{format_moeda(filho['parcial_real'])}</span>", unsafe_allow_html=True)
                            f6.markdown(f"<span style='color:gray;'>REAL</span>", unsafe_allow_html=True)
                else:
                    st.write("ℹ️ Nenhum lançamento para este mês.")
            saldo_acumulado_mes = saldo_final_mes

    if st.button("Voltar ao Topo", key="btn_topo_lanc"): 
        ir_para_o_topo()