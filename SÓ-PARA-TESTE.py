import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import calendar

from orcas_v01_ajuda_conciliacao import renderizar_ajuda_conciliacao

def buscar_dados_cartao(df, nome_cartao):
    """
    Busca o dia de corte e o dia de vencimento do cartão ($CCP),
    ignorando diferenças de maiúsculas/minúsculas e espaços.
    """
    if not df.empty and 'cc_tipo' in df.columns:
        nome_busca = str(nome_cartao).strip().upper()
        
        # Filtra registros CCP exatamente do cartão solicitado
        df_ccp = df[
            (df['cc_tipo'].fillna('').astype(str).str.strip().str.upper().isin(['$CCP', 'CCP', "'Z $CCP", "Z|$CCP"])) & 
            (df['descricao'].fillna('').astype(str).str.strip().str.upper() == nome_busca)
        ]
        
        if not df_ccp.empty:
            for _, row_c in df_ccp.iterrows():
                venc = row_c.get('cc_dia_vencimento')
                corte = row_c.get('cc_dia_corte')
                
                # Garante que encontrou valores numéricos válidos
                if pd.notnull(venc) and pd.notnull(corte):
                    return int(corte), int(venc)
                elif pd.notnull(venc):
                    # Se não tem dia de corte cadastrado, assume que o corte é 10 dias antes do vencimento
                    corte_calc = int(venc) - 10 if int(venc) > 10 else int(venc) + 20
                    return corte_calc, int(venc)

    # Fallback padrão caso não encontre cadastro específico deste cartão
    return 10, 10


def calcular_vencimento_fatura(data_compra, dia_corte=10, dia_vencimento=10):
    """
    Calcula a data de vencimento da 1ª parcela com base no dia de vencimento/corte.
    Se data_compra.day >= dia_vencimento (ou corte), a 1ª parcela vai para o mês seguinte.
    """
    ano = data_compra.year
    mes = data_compra.month

    # Usamos o menor valor entre corte e vencimento para garantir o fechamento correto
    dia_limite = min(dia_corte, dia_vencimento)

    if data_compra.day >= dia_limite:
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1

    dia_final = min(dia_vencimento, calendar.monthrange(ano, mes)[1])
    return datetime(ano, mes, dia_final).date()


def somar_meses_data(data_base, qtd_meses, dia_vencimento=10):
    """Avança N meses mantendo a coerência do dia de vencimento do cartão."""
    ano = data_base.year + ((data_base.month + qtd_meses - 1) // 12)
    mes = ((data_base.month + qtd_meses - 1) % 12) + 1
    dia = min(dia_vencimento, calendar.monthrange(ano, mes)[1])
    return datetime(ano, mes, dia).date()


def buscar_cartoes_lcp(df):
    """
    Busca no DataFrame os cartões cadastrados preservando o nome original cadastrado.
    """
    cartoes_ccp = []
    if not df.empty and 'cc_tipo' in df.columns:
        df_ccp = df[df['cc_tipo'].fillna('').astype(str).str.strip().str.upper().isin(['$CCP', 'CCP', "'Z $CCP", "Z|$CCP"])]
        if not df_ccp.empty and 'descricao' in df_ccp.columns:
            cartoes_ccp = df_ccp['descricao'].dropna().unique().tolist()
            cartoes_ccp = sorted(list(set([c.strip() for c in cartoes_ccp if c.strip()])))
    
    opcoes = ["Nenhum"] + cartoes_ccp + ["+ Outro Cartão..."]
    return opcoes


def atualizar_valor_plan_cartao(supabase, df, nome_cartao, dt_vencimento, ID_USUARIO_LOGADO):
    """
    Recalcula o valor_plan do Cartão Pai ($CCP) com base na soma dos LCLs referentes ao mês de vencimento.
    """
    nome_busca = str(nome_cartao).strip().upper()
    ano_venc = dt_vencimento.year
    mes_venc = dt_vencimento.month

    # Busca se já existe registro $CCP criado para este cartão neste mês/ano
    df_ccp = df[
        (df['cc_tipo'].fillna('').astype(str).str.strip().str.upper().isin(['$CCP', 'CCP', "'Z $CCP", "Z|$CCP"])) &
        (df['descricao'].fillna('').astype(str).str.strip().str.upper() == nome_busca) &
        (pd.to_datetime(df['data_vencimento']).dt.year == ano_venc) &
        (pd.to_datetime(df['data_vencimento']).dt.month == mes_venc)
    ]

    # Soma todos os LCLs (parcelas do cartão) deste cartão com vencimento neste mês/ano
    # Abrangendo variações comuns de gravação (LCL, 'Z LCL, $CCL, etc)
    mask_lcls = (
        (df['cc_tipo'].fillna('').astype(str).str.strip().str.upper().str.contains('LCL|\$CCL', regex=True)) &
        (df['descricao'].fillna('').astype(str).str.strip().str.upper() == nome_busca) &
        (pd.to_datetime(df['data_vencimento']).dt.year == ano_venc) &
        (pd.to_datetime(df['data_vencimento']).dt.month == mes_venc)
    )
    
    soma_lcls = float(df[mask_lcls]['valor_plan'].sum()) if not df.empty else 0.0

    try:
        if not df_ccp.empty:
            id_ccp = df_ccp.iloc[0]['id']
            supabase.table("lancamentos").update({
                "valor_plan": round(soma_lcls, 2)
            }).eq("id", id_ccp).execute()
        else:
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


def exibir_conciliacao(df, supabase, ID_USUARIO_LOGADO, format_moeda, parse_moeda):
    """
    Sub-rotina da Tela Conciliação - Regras estritas de LOU, LPR e LCL com cartões $CCP.
    """
    st.markdown("""
        <style>
        div[data-testid="stColumn"] div.stButton > button {
            padding: 2px 4px !important;
            min-width: 32px !important;
            height: 28px !important;
            font-size: 11px !important;
            white-space: nowrap !important;
        }
        </style>
    """, unsafe_allow_html=True)

    if "reset_count" not in st.session_state:
        st.session_state.reset_count = 0

    reset_key = st.session_state.reset_count

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

    hoje_c = (datetime.utcnow() - timedelta(hours=3)).date()
    ini_mes_c = hoje_c.replace(day=1)
    limite_c = hoje_c - timedelta(days=4)

    col_aviso, col_tog = st.columns([4, 3])
    col_aviso.markdown('<div style="font-size: 0.8rem; color: #555; margin-top: 10px;">📱🔄 SE USANDO O CELULAR, TRABALHE COM ELE NA HORIZONTAL</div>', unsafe_allow_html=True)
    
    abrir_sem_plan = col_tog.toggle("Lançar sem Planejamento", value=st.session_state.get('abrir_sem_plan', False))
    st.session_state.abrir_sem_plan = abrir_sem_plan
    
    listar_todos_mes = col_tog.toggle("Listar todos Lançamentos do mês", value=st.session_state.get('listar_todos_mes', False))
    st.session_state.listar_todos_mes = listar_todos_mes
    
    st.divider()

    lista_cartoes_ccp = buscar_cartoes_lcp(df)

    # --- ÁREA: LANÇAR SEM PLANEJAMENTO ---
    if st.session_state.abrir_sem_plan:
        cols_sp = st.columns([1.8, 0.8, 1.0, 1.3, 0.6, 0.5], vertical_alignment="center")
        sp_desc = cols_sp[0].text_input("Descrição", key=f"sp_desc_{reset_key}", placeholder="Ex: Combustível")
        sp_tipo = cols_sp[1].selectbox("E/S", ["Saída", "Entrada"], key=f"sp_tipo_{reset_key}")
        sp_valor = cols_sp[2].text_input("Valor Real", key=f"sp_valor_{reset_key}", value="0,00")
        
        sp_cartao_sel = cols_sp[3].selectbox("Cartão", lista_cartoes_ccp, key=f"sp_cartao_sel_{reset_key}")
        sp_parc = cols_sp[4].number_input("Parc.", min_value=0, max_value=12, value=0, step=1, key=f"sp_parc_{reset_key}")
        
        sp_cartao_manual = ""
        if sp_cartao_sel == "+ Outro Cartão...":
            sp_cartao_manual = st.text_input("Nome do Cartão", key=f"sp_cartao_manual_input_{reset_key}", placeholder="Ex: ITAÚ MASTER")

        with cols_sp[5]:
            st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
            btn_confirmar = st.button("Ok", key=f"btn_sp_conf_{reset_key}", use_container_width=True)
        
        if btn_confirmar:
            v_sp = parse_moeda(sp_valor)
            if sp_desc and v_sp > 0:
                nome_cartao_final = sp_cartao_manual.strip() if sp_cartao_sel == "+ Outro Cartão..." else sp_cartao_sel
                
                is_cc = bool(nome_cartao_final) and nome_cartao_final != "Nenhum" and int(sp_parc) > 0
                qtd_p = int(sp_parc) if is_cc else 0

                try:
                    # Se for Cartão de Crédito, a compra original fica com valor_real = 0 para NÃO duplicar a saída no mês atual!
                    v_real_lancamento = 0.0 if is_cc else float(v_sp)
                    status_lancamento = "Planejado" if is_cc else "Realizado"

                    supabase.table("lancamentos").insert({
                        "projeto_id": str(st.session_state.projeto_ativo),
                        "usuario_id": str(ID_USUARIO_LOGADO),
                        "descricao": sp_desc,
                        "data": hoje_c.strftime('%Y-%m-%d'),
                        "data_vencimento": hoje_c.strftime('%Y-%m-%d'),
                        "tipo": sp_tipo,
                        "valor_plan": 0.0, 
                        "valor_real": v_real_lancamento,
                        "status": status_lancamento, 
                        "parcial_real": 0.0, 
                        "permite_parcial": False,
                        "cc_tipo": "LCL" if is_cc else None,
                        "cc_qtd_parcelas": qtd_p
                    }).execute()

                    if is_cc:
                        corte, venc = buscar_dados_cartao(df, nome_cartao_final)
                        base_val = round(float(v_sp) / qtd_p, 2)
                        residuo = round(float(v_sp) - (base_val * qtd_p), 2)
                        
                        dt_primeiro_venc = calcular_vencimento_fatura(hoje_c, dia_corte=corte, dia_vencimento=venc)

                        for i in range(qtd_p):
                            v_parcela = base_val + (residuo if i == (qtd_p - 1) else 0.0)
                            dt_venc_parc = somar_meses_data(dt_primeiro_venc, i, dia_vencimento=venc)
                            parc_str = f"{i+1:02d}/{qtd_p:02d}"
                            
                            supabase.table("lancamentos").insert({
                                "projeto_id": str(st.session_state.projeto_ativo),
                                "usuario_id": str(ID_USUARIO_LOGADO),
                                "descricao": nome_cartao_final,
                                "cc_descricao": f"{sp_desc} ({parc_str})",
                                "data": dt_venc_parc.strftime('%Y-%m-%d'),
                                "data_vencimento": dt_venc_parc.strftime('%Y-%m-%d'),
                                "cc_data_compra": hoje_c.strftime('%Y-%m-%d'),
                                "tipo": "Saída",
                                "valor_plan": round(v_parcela, 2),
                                "valor_real": 0.0,
                                "status": "Planejado",
                                "cc_tipo": "LCL",
                                "cc_qtd_parcelas": 0
                            }).execute()

                            atualizar_valor_plan_cartao(supabase, df, nome_cartao_final, dt_venc_parc, ID_USUARIO_LOGADO)

                    st.session_state.reset_count += 1
                    st.session_state.abrir_sem_plan = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao realizar lançamento sem planejamento: {e}")

        st.divider()

    df_c = df.copy()
    if not df_c.empty:
        df_c['dt_obj'] = pd.to_datetime(df_c['data']).dt.date
        df_c['parcial_real'] = pd.to_numeric(df_c['parcial_real'], errors='coerce').fillna(0)
        
        df_base_tela = df_c[(df_c['parcial_real'] == 0) & (~df_c['cc_tipo'].fillna('').astype(str).str.strip().str.upper().str.contains('LCL|\$CCL', regex=True))].copy()
        
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

        h1, h2, h3, h4, h5, h6, h7, h8 = st.columns([2.2, 0.4, 0.9, 0.9, 0.9, 1.2, 0.5, 0.7], vertical_alignment="center")
        h1.write("**Data - Descrição**")
        h2.write("**E/S**")
        h3.write("**V. Plan.**")
        h4.write("**V. Real**")
        h5.write("**V. Parcial**")
        h6.write("**Cartão**")
        h7.write("**Parc.**")
        h8.write("**Ação**")
        st.divider()

        for _, row in df_final_concilia.iterrows():
            v_acumulado_desc = df[df['descricao'] == row['descricao']]['parcial_real'].fillna(0).sum()
            cor_txt = "red" if (row['valor_plan'] > 0 and v_acumulado_desc > row['valor_plan']) else "black"
            
            st.markdown('<div style="margin-bottom: -32px;"></div>', unsafe_allow_html=True)
            
            c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([2.2, 0.4, 0.9, 0.9, 0.9, 1.2, 0.5, 0.7], vertical_alignment="center")
            
            c1.markdown(f"<span style='color:{cor_txt}; font-weight: 500;'>{row['dt_obj'].strftime('%d/%m/%Y')} - {row['descricao']}</span>", unsafe_allow_html=True)
            cor_tipo = 'red' if row['tipo'] == 'Saída' else 'blue'
            c2.markdown(f"<span style='color:{cor_tipo}'>{row['tipo'][0]}</span>", unsafe_allow_html=True)
            
            valor_exibicao_real = row['valor_real']
            if str(row.get('cc_tipo')).strip().upper() in ['$CCP', 'CCP', "'Z $CCP", "Z|$CCP"]:
                soma_lcls = df[
                    (df['cc_tipo'].fillna('').astype(str).str.strip().str.upper().str.contains('LCL|\$CCL', regex=True)) & 
                    (df['descricao'].fillna('').astype(str).str.strip().str.upper() == str(row['descricao']).strip().upper()) & 
                    (pd.to_datetime(df['data_vencimento']).dt.month == row['dt_obj'].month) &
                    (pd.to_datetime(df['data_vencimento']).dt.year == row['dt_obj'].year)
                ]['valor_real'].sum()
                valor_exibicao_real = soma_lcls

            if row['permite_parcial']:
                c3.markdown(f"<span style='color:{cor_txt}'>{format_moeda(row['valor_plan'])}</span>", unsafe_allow_html=True)
                c4.markdown(f"<span style='color:{cor_txt}'>{format_moeda(v_acumulado_desc)}</span>", unsafe_allow_html=True)
                
                v_key = f"v_p_{row['id']}"
                if v_key not in st.session_state: 
                    st.session_state[v_key] = 0
                
                v_parc_in = c5.text_input("", key=f"p_{row['id']}_{reset_key}_{st.session_state[v_key]}", value="0,00", label_visibility="collapsed")
                
                cc_sel = c6.selectbox("", lista_cartoes_ccp, key=f"cc_p_sel_{row['id']}_{reset_key}", label_visibility="collapsed")
                qtd_parc_in = c7.number_input("", min_value=0, max_value=12, value=0, step=1, key=f"q_p_{row['id']}_{reset_key}", label_visibility="collapsed")

                cc_outro_nome = ""
                if cc_sel == "+ Outro Cartão...":
                    cc_outro_nome = st.text_input("Digite o Cartão", key=f"cc_outro_p_{row['id']}_{reset_key}", placeholder="Ex: ITAÚ MASTER")

                if c8.button("Ok", key=f"btn_p_{row['id']}", use_container_width=True):
                    v_dig = parse_moeda(v_parc_in)
                    if v_dig > 0:
                        nome_cartao_final = cc_outro_nome.strip() if cc_sel == "+ Outro Cartão..." else cc_sel
                        is_cc = bool(nome_cartao_final) and nome_cartao_final != "Nenhum" and int(qtd_parc_in) > 0
                        qtd_p = int(qtd_parc_in) if is_cc else 0

                        try:
                            supabase.table("lancamentos").insert({
                                "projeto_id": str(st.session_state.projeto_ativo),
                                "usuario_id": str(ID_USUARIO_LOGADO), 
                                "descricao": row['descricao'], 
                                "data": ini_mes_c.strftime('%Y-%m-%d'), 
                                "data_vencimento": ini_mes_c.strftime('%Y-%m-%d'), 
                                "tipo": row['tipo'],
                                "valor_plan": 0.0, 
                                "valor_real": 0.0 if is_cc else float(v_dig), 
                                "status": "Planejado" if is_cc else "Realizado",
                                "parcial_real": float(v_dig), 
                                "parcial_data": hoje_c.strftime('%Y-%m-%d'), 
                                "permite_parcial": False,
                                "cc_tipo": "LCL" if is_cc else None,
                                "cc_qtd_parcelas": qtd_p
                            }).execute()

                            if is_cc:
                                corte, venc = buscar_dados_cartao(df, nome_cartao_final)
                                base_val = round(float(v_dig) / qtd_p, 2)
                                residuo = round(float(v_dig) - (base_val * qtd_p), 2)
                                
                                dt_primeiro_venc = calcular_vencimento_fatura(hoje_c, dia_corte=corte, dia_vencimento=venc)
                                
                                for i in range(qtd_p):
                                    v_parcela = base_val + (residuo if i == (qtd_p - 1) else 0.0)
                                    dt_venc_parc = somar_meses_data(dt_primeiro_venc, i, dia_vencimento=venc)
                                    parc_str = f"{i+1:02d}/{qtd_p:02d}"
                                    
                                    supabase.table("lancamentos").insert({
                                        "projeto_id": str(st.session_state.projeto_ativo),
                                        "usuario_id": str(ID_USUARIO_LOGADO),
                                        "descricao": nome_cartao_final,
                                        "cc_descricao": f"{row['descricao']} ({parc_str})",
                                        "data": dt_venc_parc.strftime('%Y-%m-%d'),
                                        "data_vencimento": dt_venc_parc.strftime('%Y-%m-%d'),
                                        "cc_data_compra": hoje_c.strftime('%Y-%m-%d'),
                                        "tipo": "Saída",
                                        "valor_plan": round(v_parcela, 2),
                                        "valor_real": 0.0,
                                        "status": "Planejado",
                                        "cc_tipo": "LCL",
                                        "cc_qtd_parcelas": 0
                                    }).execute()

                                    atualizar_valor_plan_cartao(supabase, df, nome_cartao_final, dt_venc_parc, ID_USUARIO_LOGADO)

                            st.session_state.reset_count += 1
                            st.session_state[v_key] += 1
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar pagamento parcial: {e}")
            else:
                c3.write(format_moeda(row['valor_plan']))
                if row['status'] in ['Realizado', 'REAL']:
                    c4.write(format_moeda(valor_exibicao_real))
                    c5.write("-")
                    c6.write("-")
                    c7.write("-")
                    c8.write("✅")
                else:
                    v_norm_in = c4.text_input("", key=f"n_{row['id']}_{reset_key}", value="0,00", label_visibility="collapsed")
                    c5.write("-")
                    
                    cc_norm_sel = c6.selectbox("", lista_cartoes_ccp, key=f"cc_n_sel_{row['id']}_{reset_key}", label_visibility="collapsed")
                    qtd_norm_in = c7.number_input("", min_value=0, max_value=12, value=0, step=1, key=f"q_n_{row['id']}_{reset_key}", label_visibility="collapsed")

                    cc_norm_outro_nome = ""
                    if cc_norm_sel == "+ Outro Cartão...":
                        cc_norm_outro_nome = st.text_input("Digite o Cartão", key=f"cc_outro_n_{row['id']}_{reset_key}", placeholder="Ex: ITAÚ MASTER")

                    if c8.button("Ok", key=f"btn_n_{row['id']}", use_container_width=True):
                        v_para_gravar = parse_moeda(v_norm_in)
                        if v_para_gravar == 0: 
                            v_para_gravar = row['valor_plan']
                        
                        nome_cartao_final = cc_norm_outro_nome.strip() if cc_norm_sel == "+ Outro Cartão..." else cc_norm_sel
                        is_cc = bool(nome_cartao_final) and nome_cartao_final != "Nenhum" and int(qtd_norm_in) > 0
                        qtd_p = int(qtd_norm_in) if is_cc else 0

                        try:
                            # Se for cartão de crédito, o lançamento original fica com valor_real = 0 e status "Planejado"
                            # assim o gasto não entra como saída no mês atual e vai 100% para a fatura do cartão
                            v_update_real = 0.0 if is_cc else float(v_para_gravar)
                            status_update = "Planejado" if is_cc else "Realizado"

                            supabase.table("lancamentos").update({
                                "valor_real": v_update_real, 
                                "status": status_update,
                                "cc_tipo": "LCL" if is_cc else None,
                                "cc_qtd_parcelas": qtd_p
                            }).eq("id", row['id']).execute()

                            if is_cc:
                                corte, venc = buscar_dados_cartao(df, nome_cartao_final)
                                base_val = round(float(v_para_gravar) / qtd_p, 2)
                                residuo = round(float(v_para_gravar) - (base_val * qtd_p), 2)
                                
                                dt_primeiro_venc = calcular_vencimento_fatura(row['dt_obj'], dia_corte=corte, dia_vencimento=venc)

                                for i in range(qtd_p):
                                    v_parcela = base_val + (residuo if i == (qtd_p - 1) else 0.0)
                                    dt_venc_parc = somar_meses_data(dt_primeiro_venc, i, dia_vencimento=venc)
                                    parc_str = f"{i+1:02d}/{qtd_p:02d}"
                                    
                                    supabase.table("lancamentos").insert({
                                        "projeto_id": str(st.session_state.projeto_ativo),
                                        "usuario_id": str(ID_USUARIO_LOGADO),
                                        "descricao": nome_cartao_final,
                                        "cc_descricao": f"{row['descricao']} ({parc_str})",
                                        "data": dt_venc_parc.strftime('%Y-%m-%d'),
                                        "data_vencimento": dt_venc_parc.strftime('%Y-%m-%d'),
                                        "cc_data_compra": row['dt_obj'].strftime('%Y-%m-%d'),
                                        "tipo": "Saída",
                                        "valor_plan": round(v_parcela, 2),
                                        "valor_real": 0.0,
                                        "status": "Planejado",
                                        "cc_tipo": "LCL",
                                        "cc_qtd_parcelas": 0
                                    }).execute()

                                    atualizar_valor_plan_cartao(supabase, df, nome_cartao_final, dt_venc_parc, ID_USUARIO_LOGADO)

                            st.session_state.reset_count += 1
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar conciliação: {e}")
            st.divider()
    else:
        st.info("Nenhum lançamento pendente para conciliação.")