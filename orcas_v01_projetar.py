import streamlit as st
from datetime import datetime, timedelta, timezone
import re

def exibir_projetar(df, supabase, ID_USUARIO_LOGADO, d_fim_db, parse_moeda):
    st.markdown(f'<div class="titulo-tela">Projetar: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    # Ajuste de Fuso Horário para Jundiaí/Brasília (UTC-3)
    fuso_br = timezone(timedelta(hours=-3))
    hoje_br = datetime.now(fuso_br).date()

    if 'limpar_cont' not in st.session_state:
        st.session_state.limpar_cont = 0
    if 'bloqueio_excludente' not in st.session_state:
        st.session_state.bloqueio_excludente = False

    # Busca segura da mensagem de sucesso
    if st.session_state.get('msg_sucesso'): 
        st.success(st.session_state['msg_sucesso'])
        st.session_state['msg_sucesso'] = None

    # --- (1) TRAVA DE SEGURANÇA EXCLUDENTE ---
    if st.session_state.bloqueio_excludente:
        st.error("AS OPÇÕES (DIA DO MÊS, DIA DA SEMANA E DIA ESPECÍFICO) SÃO EXCLUDENTES E PORTANTO O ORCAS ACEITARÁ APENAS UMA DELAS")
        if st.button("OK", key="btn_ok_erro"):
            st.session_state.bloqueio_excludente = False
            st.session_state.limpar_cont += 1
            st.rerun()
        st.stop()

    v = st.session_state.limpar_cont

    col_d1, col_d2 = st.columns([4, 2])
    desc = col_d1.text_input("Descrição", key=f"pj_d_{v}")
    comp_txt = col_d2.text_input("Complemento", key=f"pj_comp_{v}")
    
    col_v, col_t = st.columns(2)
    v_t = col_v.text_input("Valor", "0,00", key=f"pj_val_{v}")
    tipo = col_t.selectbox("Tipo", ["Saída", "Entrada"], key=f"pj_tipo_{v}")

    with st.expander("Recorrência e Datas"):
        c1, c2, c3 = st.columns(3)
        d_m = c1.text_input("Dia (1-31, DD/MM ou *)", "", key=f"pj_dm_{v}")
        d_s = c2.selectbox("Dia da Semana", ["", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"], key=f"pj_ds_{v}")
        d_e = c3.date_input("Dia Específico", value=None, format="DD/MM/YYYY", key=f"pj_de_{v}")
        
        op_preenchidas = 0
        if d_m != "": op_preenchidas += 1
        if d_s != "": op_preenchidas += 1
        if d_e is not None: op_preenchidas += 1
        
        if op_preenchidas > 1:
            st.session_state.bloqueio_excludente = True
            st.rerun()
            
        n_ocorrencias = st.number_input("Nº de Ocorrências (0 = usar Data Até)", min_value=0, step=1, key=f"pj_noc_{v}")
        fds = st.radio("Se cair em Fim de Semana:", ["Manter", "Antecipa", "Posterga"], horizontal=True, key=f"pj_fds_{v}")
        
        c_i, c_f = st.columns(2)
        i_p = c_i.date_input("Início", value=hoje_br, format="DD/MM/YYYY", key=f"pj_data_ini_{v}")
        f_p = c_f.date_input("Até", value=d_fim_db if d_fim_db else hoje_br, format="DD/MM/YYYY", key=f"pj_data_fim_{v}")

    with st.expander("🛠️ Projeção Avançada", expanded=False):
        st.markdown("**Regras de Correção Automática**")
        col_c1, col_c2, col_c3 = st.columns([2, 2, 3])
        usar_corrc = col_c1.checkbox("Corrigir este valor?", key=f"pj_cor_{v}")
        c_quando = col_c2.selectbox("Quando:", ["Todo mês", "Todo ano"], key=f"pj_qdo_{v}")
        c_base = col_c3.selectbox("Com base em:", ["Média dos Realizados", "Percentual Fixo (%)", "IGPM"], key=f"pj_base_{v}")
        c_val_fixo = st.text_input("Valor do Percentual (se fixo)", "0,00", key=f"pj_vfixo_{v}")

        st.divider()
        st.markdown("**Realizações Parciais e Resíduos**")
        col_p1, col_p2 = st.columns([2, 5])
        permitir_parcial = col_p1.checkbox("Permitir parciais?", key=f"pj_parc_{v}")
        
        opcoes_residuo = [
            "Zera o Realizado", 
            "Adicione a diferença (P-R) no próximo Planejado", 
            "Copia a diferença (P-R) no próximo Planejado"
        ]
        p_depois = col_p2.selectbox("No último dia do Mês:", opcoes_residuo, index=0, key=f"pj_pdep_{v}")

    btn_col1, btn_col2, _ = st.columns([1, 1, 2])

    if btn_col1.button("Incluir", use_container_width=True):
        if not desc or desc.strip() == "":
            st.error("PARA INCLUIR OU EXCLUIR É OBRIGATÓRIO ENTRAR COM UMA DESCRIÇÃO")
        else:
            d_m_final = d_m
            if permitir_parcial:
                d_m_final = "1"

            # TRAVA 1: O loop começa na data de Início (i_p).
            # Se for parcial, forçamos o início do loop para o dia 01 do mês de i_p para não pular o mês atual.
            curr = i_p
            if permitir_parcial:
                curr = curr.replace(day=1)

            uid_local = st.session_state.get('CHAVE_MESTRA_UUID')
            v_calc = parse_moeda(v_t)
            v_pct = parse_moeda(c_val_fixo) / 100
            lista_bulk = [] 
            gerados = 0
            d_map = {"Segunda":0,"Terça":1,"Quarta":2,"Quinta":3,"Sexta":4,"Sábado":5,"Domingo":6}
            
            # --- LÓGICA DE INCREMENTO DO COMPLEMENTO ---
            comp_base = comp_txt.strip() if comp_txt else ""
            num_atual = None
            sufixo = ""
            zeros = 0
            
            if comp_base:
                match_de = re.search(r'(\d+)(\s+de\s+.*)', comp_base, re.IGNORECASE)
                if match_de:
                    num_str = match_de.group(1)
                    num_atual = int(num_str)
                    zeros = len(num_str)
                    sufixo = match_de.group(2)
                elif comp_base.isdigit():
                    num_atual = int(comp_base)
                    zeros = len(comp_base)

            # O limite é a data Fim (f_p)
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
                    
                    # TRAVA 2: Só processa se curr estiver estritamente dentro do intervalo de validade
                    # Para parciais, validamos apenas se o mês/ano de curr é >= ao mês/ano de i_p
                    processar = False
                    if permitir_parcial:
                        # Se permitir parcial, o dia de curr é sempre 1. Validamos se esse dia 1 está no período.
                        dt_ref_parcial = curr.replace(day=1)
                        if i_p.replace(day=1) <= dt_ref_parcial <= f_p:
                            processar = True
                    else:
                        if i_p <= curr <= f_p:
                            processar = True

                    if processar:
                        dt_f = curr
                        if permitir_parcial:
                            dt_f = dt_f.replace(day=1)
                        elif fds != "Manter" and dt_f.weekday() >= 5: 
                            if fds == "Posterga":
                                dt_f += timedelta(days=(2 if dt_f.weekday()==5 else 1))
                            elif fds == "Antecipa":
                                # Ajuste: Se domingo (6), volta 2 dias para sexta. Se sábado (5), volta 1 dia para sexta.
                                dt_f -= timedelta(days=(1 if dt_f.weekday()==5 else 2))
                        
                        # TRAVA 3: Valida novamente após ajuste de FDS (apenas para não parciais)
                        if permitir_parcial or (i_p <= dt_f <= f_p):
                            # Gera o texto do complemento para este item
                            comp_gerado = comp_txt
                            if num_atual is not None:
                                comp_gerado = f"{str(num_atual + gerados).zfill(zeros)}{sufixo}"

                            nome_final = f"{desc} {comp_gerado}".strip() if comp_gerado else desc
                            
                            lista_bulk.append({
                                "projeto_id": st.session_state.projeto_ativo, 
                                "usuario_id": uid_local, 
                                "data": dt_f.strftime('%Y-%m-%d'), 
                                "data_vencimento": dt_f.strftime('%Y-%m-%d'),
                                "descricao": nome_final, 
                                "valor_plan": float(v_calc), 
                                "valor_real": 0.0, 
                                "tipo": tipo, 
                                "status": 'Planejado', 
                                "permite_parcial": bool(permitir_parcial),
                                "usar_media": bool(usar_corrc and c_base == "Média dos Realizados"),
                                "complemento_texto": comp_gerado if comp_gerado else None,
                                "correcao_freq": c_quando if usar_corrc else None,
                                "correcao_valor": float(v_pct) if c_base == "Percentual Fixo (%)" else 0.0,
                                "regra_parcial": str(p_depois)
                            })
                            gerados += 1
                            if usar_corrc and c_quando == "Todo mês" and c_base == "Percentual Fixo (%)": v_calc *= (1 + v_pct)

                if n_ocorrencias > 0 and gerados >= n_ocorrencias: break
                curr += timedelta(days=1)
            
            if lista_bulk:
                try:
                    supabase.table("lancamentos").insert(lista_bulk).execute()
                    st.session_state['msg_sucesso'] = f"Sucesso! {len(lista_bulk)} lançamentos gerados."
                    st.session_state.limpar_cont += 1
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro no Supabase: {e}")
            else:
                st.warning("Nenhum lançamento gerado. As datas da regra caem fora do intervalo Início/Até.")

    if btn_col2.button("Excluir", use_container_width=True):
        if not desc or desc.strip() == "": 
            st.error("PARA INCLUIR OU EXCLUIR É OBRIGATÓRIO ENTRAR COM UMA DESCRIÇÃO")
        else:
            st.session_state.confirmar_exclusao_ativa = True

    if st.session_state.get('confirmar_exclusao_ativa', False):
        nome_busca = f"{desc} {comp_txt}".strip() if comp_txt else desc
        uid_exec = st.session_state.get('CHAVE_MESTRA_UUID') 
        msg_confirma = f"VOCÊ DESEJA EXCLUIR O LANÇAMENTO {nome_busca} DO DIA {d_e.strftime('%d/%m/%Y') if d_e else ''}. SIM/NÃO?" if d_e else f"VOCÊ DESEJA EXCLUIR TODOS OS LANÇAMENTOS DE {nome_busca} DO PERÍODO DE {i_p.strftime('%d/%m/%Y')} A {f_p.strftime('%d/%m/%Y')}. SIM/NÃO?"
        st.warning(msg_confirma)
        exc_c1, exc_c2 = st.columns(2)
        if exc_c1.button("SIM", key="btn_conf_sim"):
            query = supabase.table("lancamentos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid_exec).eq("descricao", nome_busca)
            if d_e:
                res_exc = query.eq("data", d_e.strftime('%Y-%m-%d')).execute()
            else:
                res_exc = query.gte("data", i_p.strftime('%Y-%m-%d')).lte("data", f_p.strftime('%Y-%m-%d')).execute()
            
            qtd_excluidos = len(res_exc.data) if hasattr(res_exc, 'data') else 0
            st.session_state['msg_sucesso'] = f"Sucesso! {qtd_excluidos} Lançamentos Excluídos."
            st.session_state.confirmar_exclusao_ativa = False
            st.rerun()
        if exc_c2.button("NÃO", key="btn_conf_nao"):
            st.session_state.confirmar_exclusao_ativa = False
            st.rerun()