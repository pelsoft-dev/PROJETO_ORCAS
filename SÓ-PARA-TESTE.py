def atualizar_valor_plan_cartao(supabase, df, nome_cartao, dt_vencimento, ID_USUARIO_LOGADO):
    """
    Recalcula o valor_plan do Cartão Pai ($CCP) consultando diretamente o Supabase.
    Soma todas as parcelas (LCL) com vencimento no mês/ano correspondente.
    """
    nome_busca = str(nome_cartao).strip().upper()
    ano_venc = dt_vencimento.year
    mes_venc = dt_vencimento.month

    primeiro_dia_mes = f"{ano_venc:04d}-{mes_venc:02d}-01"
    ultimo_dia_mes = f"{ano_venc:04d}-{mes_venc:02d}-{calendar.monthrange(ano_venc, mes_venc)[1]:02d}"

    try:
        # Busca lançamentos atualizados diretamente do banco de dados
        res = supabase.table("lancamentos") \
            .select("id, descricao, cc_tipo, valor_plan, data_vencimento") \
            .eq("projeto_id", str(st.session_state.projeto_ativo)) \
            .gte("data_vencimento", primeiro_dia_mes) \
            .lte("data_vencimento", ultimo_dia_mes) \
            .execute()
        
        df_db = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception:
        df_db = pd.DataFrame()

    if not df_db.empty:
        # Identifica o Cartão Pai ($CCP) existente no mês
        df_ccp = df_db[
            (df_db['cc_tipo'].fillna('').astype(str).str.strip().str.upper().isin(['$CCP', 'CCP', "'Z $CCP", "Z|$CCP"])) &
            (df_db['descricao'].fillna('').astype(str).str.strip().str.upper() == nome_busca)
        ]
        
        # Filtra e soma todas as parcelas (LCL) vinculadas a este cartão no mês
        mask_lcls = (
            (df_db['cc_tipo'].fillna('').astype(str).str.strip().str.upper().str.contains('LCL|\$CCL', regex=True)) &
            (df_db['descricao'].fillna('').astype(str).str.strip().str.upper() == nome_busca)
        )
        
        # Garante a soma do 'valor_plan' dos lançamentos LCL
        soma_lcls = float(df_db[mask_lcls]['valor_plan'].fillna(0).sum())
    else:
        df_ccp = pd.DataFrame()
        soma_lcls = 0.0

    try:
        if not df_ccp.empty:
            # Atualiza o registro $CCP existente
            id_ccp = df_ccp.iloc[0]['id']
            supabase.table("lancamentos").update({
                "valor_plan": round(soma_lcls, 2)
            }).eq("id", id_ccp).execute()
        else:
            # Caso não exista o registro $CCP no mês, cria um novo
            corte, venc = buscar_dados_cartao(df, nome_cartao)
            dia_final = min(venc, calendar.monthrange(ano_venc, mes_venc)[1])
            dt_exata_ccp = datetime(ano_venc, mes_venc, dia_final).date()

            supabase.table("lancamentos").insert({
                "projeto_id": str(st.session_state.projeto_ativo),
                "usuario_id": str(ID_USUARIO_LOGADO),
                "descricao": nome_cartao,
                "data": dt_exata_ccp.strftime('%Y-%m-%d'),
                "data_vencimento": dt_exata_ccp.strftime('%Y-%m-%d'),
                "tipo": "Saída",
                "valor_plan": round(soma_lcls, 2),
                "valor_real": 0.0,
                "status": "Planejado",
                "cc_tipo": "$CCP",
                "cc_dia_corte": corte,
                "cc_dia_vencimento": venc
            }).execute()
    except Exception as e:
        st.error(f"Erro ao atualizar Cartão Pai ($CCP): {e}")