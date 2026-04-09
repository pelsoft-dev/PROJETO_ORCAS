import streamlit as st
from datetime import datetime, timedelta

def exibir_projetar(df, supabase, ID_USUARIO_LOGADO, d_fim_db, parse_moeda):
    st.markdown(f'<div class="titulo-tela">Projetar: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    # Inicializa o versionador de limpeza se não existir
    if 'limpar_cont' not in st.session_state:
        st.session_state.limpar_cont = 0

    if st.session_state.get('msg_sucesso'): 
        st.success(st.session_state['msg_sucesso'])
        st.session_state['msg_sucesso'] = None

    # O sufixo v torna a key única e força o reset quando alterado
    v = st.session_state.limpar_cont

    # --- BLOCO DE CONTROLE DE ERRO EXCLUDENTE (PROBLEMA 1) ---
    if st.session_state.get('erro_excludente', False):
        st.error("AS OPÇÕES (DIA DO MÊS, DIA DA SEMANA E DIA ESPECÍFICO) SÃO EXCLUDENTES E PORTANTO O ORCAS ACEITARÁ APENAS UMA DELAS")
        if st.button("OK", key="btn_limpar_erro"):
            st.session_state.erro_excludente = False
            st.session_state.limpar_cont += 1
            st.rerun()
        st.stop() # Interrompe a renderização do resto da tela até clicar em OK

    col_d1, col_d2 = st.columns([4, 2])
    desc = col_d1.text_input("Descrição", key=f"pj_d_{v}")
    comp_txt = col_d2.text_input("Complemento", key=f"pj_comp_{v}", help="Será adicionado ao final da descrição")
    
    col_v, col_t = st.columns(2)
    v_t = col_v.text_input("Valor", "0,00", key=f"pj_val_{v}")
    tipo = col_t.selectbox("Tipo", ["Saída", "Entrada"], key=f"pj_tipo_{v}")

    with st.expander("Recorrência e Datas"):
        c1, c2, c3 = st.columns(3)
        d_m = c1.text_input("Dia (1-31, DD/MM ou *)", "", key=f"pj_dm_{v}")
        d_s = c2.selectbox("Dia da Semana", ["", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"], key=f"pj_ds_{v}")
        d_e = c3.date_input("Dia Específico", value=None, format="DD/MM/YYYY", key=f"pj_de_{v}")
        
        n_ocorrencias = st.number_input("Nº de Ocorrências (0 = usar Data Até)", min_value=0, step=1, key=f"pj_noc_{v}")
        fds = st.radio("Se cair em Fim de Semana:", ["Manter", "Antecipa", "Posterga"], horizontal=True, key=f"pj_fds_{v}")
        
        c_i, c_f = st.columns(2)
        i_p = c_i.date_input("Início", value=datetime.now().date(), format="DD/MM/YYYY", key=f"pj_data_ini_{v}")
        f_p = c_f.date_input("Até", value=d_fim_db if d_fim_db else datetime.now().date(), format="DD/MM/YYYY", key=f"pj_data_fim_{v}")

    with st.expander("🛠️ Projeção Avançada", expanded=False):
        st.markdown("**Regras de Correção Automática**")
        col_c1, col_c2, col_c3 = st.columns([2, 2, 3])
        usar_corrc = col_c1.checkbox("Corrigir este valor?", key=f"pj_cor_{v}")
        c_quando = col_c2.selectbox("Quando:", ["Todo mês", "Todo ano"], key=f"pj_qdo_{v}")
        c_base = col_c3.selectbox("Com base em:", ["Média dos Realizados", "Percentual Fixo (%)", "IGPM"], key=f"pj_base_{v}")
        c_val_fixo = st.text_input("Valor do Percentual (se fixo)", "0,00", key=f"pj_vfixo_{v}")

        st.divider()
        st.markdown("**Realizações Parciais e Resíduos**")
        col_p1, col_p2, col_p3 = st.columns([2, 2, 3])
        permitir_parcial = col_p1.checkbox("Permitir parciais?", key=f"pj_parc_{v}")
        p_ate = col_p2.selectbox("Até:", ["Último dia do mês", "Último dia do ano", "Sempre"], key=f"pj_pate_{v}")
        p_depois = col_p3.selectbox("Depois disso:", [
            "Zera o Realizado", 
            "Adiciona a diferença no próximo Planejado",
            "Copia Planejado atualizado para o próximo"
        ], key=f"pj_pdep_{v}")

    btn_col1, btn_col2, _ = st.columns([1, 1, 2])

    if btn_col1.button("Incluir", use_container_width=True):
        if not desc or desc.strip() == "":
            st.error("PARA INCLUIR OU EXCLUIR É OBRIGATÓRIO ENTRAR COM UMA DESCRIÇÃO")
        else:
            # (1) Verificação Excludente
            opcoes_preenchidas = 0
            if d_m != "": opcoes_preenchidas += 1
            if d_s != "": opcoes_preenchidas += 1
            if d_e is not None: opcoes_preenchidas += 1
            
            if opcoes_preenchidas > 1:
                st.session_state.erro_excludente = True
                st.rerun()
            else:
                # (2) Ajuste da Lógica de Datas para Parciais e Dia 01
                d_m_final = d_m
                # Se parcial e vazio, o dia base é 1.
                if permitir_parcial and d_m == "":
                    d_m_final = "1"
                
                uid_local = st.session_state.get('CHAVE_MESTRA_UUID')
                v_calc = parse_moeda(v_t)
                v_pct = parse_moeda(c_val_fixo) / 100
                
                # Para garantir o dia 01 do mês atual (mesmo que passado), começamos do dia 1 do mês de i_p
                curr = i_p.replace(day=1) if (permitir_parcial and d_m == "") else i_p
                
                lista_bulk = [] 
                gerados = 0
                d_map = {"Segunda":0,"Terça":1,"Quarta":2,"Quinta":3,"Sexta":4,"Sábado":5,"Domingo":6}
                
                limite_loop = f_p if n_ocorrencias == 0 else i_p + timedelta(days=3650)

                while curr <= limite_loop:
                    match_dm = False
                    if "/" in d_m_final:
                        try:
                            dia_a, mes_a = map(int, d_m_final.split("/"))
                            if curr.day == dia_a and curr.month == mes_a: match_dm = True
                        except: pass
                    else:
                        match_dm = (d_m_final == "" or d_m_final == "*" or str(curr.day) == d_m_final)

                    if (d_e is None or curr == d_e) and match_dm and (d_s == "" or curr.weekday() == d_map[d_s]):
                        # Adicionamos o lançamento se a data for >= i_p OU se for o dia 01 forçado do mês inicial
                        if curr >= i_p or (permitir_parcial and d_m == "" and curr == i_p.replace(day=1)):
                            dt_f = curr
                            if permitir_parcial:
                                dt_f = dt_f.replace(day=1)
                            elif fds != "Manter" and dt_f.weekday() >= 5: 
                                dt_f += timedelta(days=(2 if dt_f.weekday()==5 else 1) if fds=="Posterga" else -1)
                            
                            nome_final = f"{desc} {comp_txt}".strip() if comp_txt else desc
                            lista_bulk.append({
                                "projeto_id": st.session_state.projeto_ativo, 
                                "usuario_id": uid_local, 
                                "data": dt_f.strftime('%Y-%m-%d'), 
                                "data_vencimento": dt_f.strftime('%Y-%m-%d'),
                                "descricao": nome_final, 
                                "valor_plan": v_calc, 
                                "valor_real": 0.0, 
                                "tipo": tipo, 
                                "status": 'Planejado',
                                "permite_parcial": permitir_parcial,
                                "usar_media": (usar_corrc and c_base == "Média dos Realizados"),
                                "complemento_texto": comp_txt if comp_txt else None,
                                "correcao_freq": c_quando if usar_corrc else None,
                                "correcao_valor": v_pct if c_base == "Percentual Fixo (%)" else 0.0
                            })
                            gerados += 1
                            if usar_corrc and c_quando == "Todo mês" and c_base == "Percentual Fixo (%)": v_calc *= (1 + v_pct)

                    if n_ocorrencias > 0 and gerados >= n_ocorrencias: break
                    curr += timedelta(days=1)
                
                if lista_bulk:
                    supabase.table("lancamentos").insert(lista_bulk).execute()
                    st.session_state['msg_sucesso'] = f"Sucesso! {len(lista_bulk)} lançamentos gerados."
                    st.session_state.limpar_cont += 1
                    st.rerun()

    if btn_col2.button("Excluir", use_container_width=True):
        if not desc or desc.strip() == "": 
            st.error("PARA INCLUIR OU EXCLUIR É OBRIGATÓRIO ENTRAR COM UMA DESCRIÇÃO")
        else:
            st.session_state.confirmar_exclusao_ativa = True

    if st.session_state.get('confirmar_exclusao_ativa', False):
        nome_busca = f"{desc} {comp_txt}".strip() if comp_txt else desc
        uid_exec = st.session_state.get('CHAVE_MESTRA_UUID') 
        
        if d_e:
            msg_confirma = f"VOCÊ DESEJA EXCLUIR O LANÇAMENTO {nome_busca} DO DIA {d_e.strftime('%d/%m/%Y')}. SIM/NÃO?"
        else:
            msg_confirma = f"VOCÊ DESEJA EXCLUIR TODOS OS LANÇAMENTOS DE {nome_busca} DO PERÍODO DE {i_p.strftime('%d/%m/%Y')} A {f_p.strftime('%d/%m/%Y')}. SIM/NÃO?"
        
        st.warning(msg_confirma)
        exc_c1, exc_c2 = st.columns(2)
        
        if exc_c1.button("SIM", key="btn_confirm_exc_sim"):
            query = supabase.table("lancamentos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid_exec).eq("descricao", nome_busca)
            
            if d_e:
                res_exc = query.eq("data", d_e.strftime('%Y-%m-%d')).execute()
            else:
                res_exc = query.gte("data", i_p.strftime('%Y-%m-%d')).lte("data", f_p.strftime('%Y-%m-%d')).execute()
            
            num_excluidos = len(res_exc.data) if res_exc.data else 0
            st.session_state['msg_sucesso'] = f"Sucesso! {num_excluidos} lançamentos excluídos com sucesso."
            st.session_state.confirmar_exclusao_ativa = False
            st.rerun()
            
        if exc_c2.button("NÃO", key="btn_confirm_exc_nao"):
            st.session_state.confirmar_exclusao_ativa = False
            st.rerun()