import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta

# Importando a ajuda do arquivo dedicado
from orcas_v01_ajuda_gestao import renderizar_ajuda_gestao

def ao_mudar_nome_campo_02():
    """
    Força a alteração da versão do formulário e REINICIA
    a execução do Streamlit imediatamente.
    """
    st.session_state["form_version"] = st.session_state.get("form_version", 0) + 1
    # Força a interrupção do ciclo atual e reexecuta com a nova versão de keys
    st.rerun()

def exibir_gestao(supabase, ID_USUARIO_LOGADO, projs, d_ini_db, d_fim_db, s_db, format_moeda, parse_moeda, security):
    """
    Sub-rotina da Tela Gestão - Versão com Reset Instantâneo via Rerun
    """
    hoje = datetime.now().date()
    uid_gestao = ID_USUARIO_LOGADO

    # Controle de versão das keys dos widgets
    if "form_version" not in st.session_state:
        st.session_state["form_version"] = 0

    ver = st.session_state["form_version"]

    # --- 1. TRATAMENTO DO PERFIL DO UTILIZADOR E VALOR PAGO REAL ---
    tipo_renov_original = "Mensal"
    vencimento_atual_str = None
    valor_pago_real = 0.00
    data_ult_assinat_real = None
    ult_valor_mensal_lido = 0.00 
    
    try:
        res_user_master = supabase.table("usuarios").select("*").eq("id", ID_USUARIO_LOGADO).execute()
        if res_user_master and hasattr(res_user_master, 'data') and len(res_user_master.data) > 0:
            dados_usuario = res_user_master.data[0]
            vencimento_atual_str = dados_usuario.get('vencimento')
            valor_pago_real = float(dados_usuario.get('valor_pago') or 0.00)
            ult_valor_mensal_lido = float(dados_usuario.get('ult_valor_mensal') or 0.00)
            
            data_pag_aux = dados_usuario.get('data_ult_assinat') or dados_usuario.get('criado_em')
            if data_pag_aux:
                data_ult_assinat_real = datetime.strptime(str(data_pag_aux)[:10], '%Y-%m-%d').date()
            
            val_db = dados_usuario.get('tipo_renovacao')
            if val_db is not None:
                tipo_renov_original = str(val_db).strip()
    except Exception:
        tipo_renov_original = "Mensal"

    if not tipo_renov_original or tipo_renov_original == "Selecione uma option...":
        tipo_renov_original = "Mensal"

    # --- 2. CABEÇALHO ALINHADO COM BOTÃO DE AJUDA ---
    col_titulo, col_ajuda = st.columns([4, 1])
    
    with col_titulo:
        st.markdown('<div class="titulo-tela" style="margin-top:0px;">Gestão de Planos e Assinaturas</div>', unsafe_allow_html=True)
        
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
            st.session_state["exibir_ajuda_gestao"] = not st.session_state.get("exibir_ajuda_gestao", False)
            st.rerun()

    # --- 3. EXIBIÇÃO DO BOX DE AJUDA VIA ARQUIVO EXTERNO ---
    if st.session_state.get("exibir_ajuda_gestao", False):
        renderizar_ajuda_gestao()

    if st.session_state.get('msg_sucesso'):
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    col_l1_1, col_l1_2 = st.columns(2)
    lista_gestao = [""] + projs
    
    # Campo 01: Seleção de plano
    plano_sel = col_l1_1.selectbox("01. Selecione um Plano já existente:", lista_gestao, key="sb_plano_gestao_unique")
    
    # Se o usuário mudou a seleção no Campo 01, sincroniza IMEDIATAMENTE com o Campo 02
    if plano_sel != st.session_state.get('ultimo_plano_c1_processado'):
        st.session_state['ultimo_plano_c1_processado'] = plano_sel
        st.session_state.projeto_ativo = plano_sel
        st.session_state["nome_plano_input_key"] = plano_sel
        st.session_state["form_version"] = ver + 1
        
        if 'tmp_fim_plano' in st.session_state: del st.session_state.tmp_fim_plano
        if 'clicou_salvar_upgrade' in st.session_state: del st.session_state.clicou_salvar_upgrade
        if 'tipo_pagamento_selecionado' in st.session_state: del st.session_state.tipo_pagamento_selecionado
        st.rerun()

    if "nome_plano_input_key" not in st.session_state:
        st.session_state["nome_plano_input_key"] = st.session_state.projeto_ativo if st.session_state.projeto_ativo else ""

    # Campo 02: Nome do plano
    nome_plano_input = col_l1_2.text_input(
        "02. Nome do Plano carregado ou Nome para criação de um novo Plano", 
        key="nome_plano_input_key",
        on_change=ao_mudar_nome_campo_02
    )

    if nome_plano_input and nome_plano_input.strip() != "":
        
        # Compara diretamente se o texto do Campo 02 difere da seleção do Campo 01
        plano_mudou = (nome_plano_input.strip() != plano_sel.strip())

        col_l2_1, col_l2_2 = st.columns(2)
        
        # Leitura dos dados no Supabase se for um plano existente
        res_cfg_plano = supabase.table("config_projetos").select("*").eq("projeto_id", nome_plano_input).eq("usuario_id", uid_gestao).execute()
        zap_plano_db = res_cfg_plano.data[0].get('zap_ativo', 0) if res_cfg_plano.data else 0
        email_plano_db = res_cfg_plano.data[0].get('email_ativo', 0) if res_cfg_plano.data else 0

        # DEFINIÇÃO RÍGIDA DOS VALORES PADRÃO
        if plano_mudou and not res_cfg_plano.data:
            # NOVO PLANO (Valores Zerados/Padrão)
            data_inicio_padrao = hoje.replace(day=1)
            saldo_inicial_padrao = "0,00"
            zap_padrao = False
            email_padrao = False
            meses_slider_padrao = 24
        else:
            # PLANO EXISTENTE (Carrega do banco)
            data_inicio_padrao = d_ini_db if d_ini_db else hoje.replace(day=1)
            data_fim_padrao = d_fim_db if d_fim_db else (data_inicio_padrao + relativedelta(months=23)).replace(day=1) + relativedelta(months=1, days=-1)
            saldo_inicial_padrao = format_moeda(s_db) if s_db is not None else "0,00"
            zap_padrao = (zap_plano_db == 1)
            email_padrao = (email_plano_db == 1)
            
            diff_edit = relativedelta(data_fim_padrao, data_inicio_padrao)
            meses_slider_padrao = (diff_edit.years * 12) + diff_edit.months + 1
            if meses_slider_padrao not in [24, 36, 48, 60]:
                meses_slider_padrao = 24

        with col_l2_1:
            d_ini_g = st.date_input(
                "03. Data de Início:", 
                value=data_inicio_padrao,
                key=f"data_ini_v{ver}", 
                format="DD/MM/YYYY"
            )
        
        with col_l2_2:
            col_fim, col_btn_per = st.columns(2)

            with col_btn_per:
                periodo_slider = st.select_slider(
                    "05. Aumentar Período (12 meses)",
                    options=[24, 36, 48, 60],
                    value=meses_slider_padrao,
                    key=f"slider_v{ver}"
                )
                nova_data_fim = (d_ini_g + relativedelta(months=periodo_slider - 1))
                nova_data_fim = (nova_data_fim.replace(day=1) + relativedelta(months=1, days=-1))
                st.session_state.tmp_fim_plano = nova_data_fim

            with col_fim:
                d_fim_g = st.date_input("04. Data de Término:", value=st.session_state.tmp_fim_plano, format="DD/MM/YYYY", disabled=True)

        col_l3_1, col_l3_2 = st.columns(2)

        saldo_input = col_l3_1.text_input("06. Saldo Inicial:", value=saldo_inicial_padrao, key=f"saldo_v{ver}")
        
        meses_total_edit = (st.session_state.tmp_fim_plano.year - d_ini_g.year) * 12 + (st.session_state.tmp_fim_plano.month - d_ini_g.month) + 1
        col_l3_2.text_input("07. Período do Plano:", value=f"{meses_total_edit} meses", disabled=True)

        col_l4_1, col_l4_2 = st.columns(2)

        if st.session_state.get("pagamento_realizado_sucesso"):
            zap_padrao = False
            email_padrao = True
            if "pagamento_realizado_sucesso" in st.session_state: del st.session_state.pagamento_realizado_sucesso
            if "meses_comprados" in st.session_state: del st.session_state.meses_comprados

        with col_l4_1:
            st.write("") 
            st.write("") 
            ativar_zap_atual = st.checkbox("08. Adicionar o Resumo Diário ORCAS via Whatsapp", value=zap_padrao, key=f"zap_v{ver}")
            ativar_email_atual = st.checkbox("09. Adicionar o Resumo Diário ORCAS via E-mail", value=email_padrao, key=f"email_v{ver}")
        
        res_all = supabase.table("config_projetos").select("*").eq("usuario_id", uid_gestao).execute()
        dados_db = res_all.data if res_all.data else []
        
        planos_banco = {}
        rels_banco = {}
        for p in dados_db:
            da1 = datetime.strptime(p['data_ini'], '%Y-%m-%d').date()
            da2 = datetime.strptime(p['data_fim'], '%Y-%m-%d').date()
            planos_banco[p['projeto_id']] = (da2.year - da1.year) * 12 + (da2.month - da1.month) + 1
            rels_banco[p['projeto_id']] = 1 if (p.get('zap_ativo', 0) == 1 or p.get('email_ativo', 0) == 1) else 0

        planos_consolidar = dict(planos_banco)
        relatorios_consolidar = dict(rels_banco)
        
        planos_consolidar[nome_plano_input] = meses_total_edit
        relatorios_consolidar[nome_plano_input] = 1 if (ativar_zap_atual or ativar_email_atual) else 0

        qtd_total_planos = len(planos_consolidar)
        qtd_relatorios_totais = sum(relatorios_consolidar.values())
        
        c24 = sum(1 for m in planos_consolidar.values() if m <= 24)
        c36 = sum(1 for m in planos_consolidar.values() if m == 36)
        c48 = sum(1 for m in planos_consolidar.values() if m == 48)
        c60 = sum(1 for m in planos_consolidar.values() if m >= 60)
        
        base_baby = 19.90 
        custo_relatorio_total = qtd_relatorios_totais * 9.85
        add_planos_extra = (qtd_total_planos - 2) * 12.80 if qtd_total_planos > 2 else 0.00
        
        v_p36 = c36 * 6.40
        v_p48 = c48 * 12.80
        v_p60 = c60 * 19.20
        
        v_mensal_total = base_baby + custo_relatorio_total + add_planos_extra + v_p36 + v_p48 + v_p60
        v_6meses = (v_mensal_total * 6) * 0.95
        v_12meses = (v_mensal_total * 12) * 0.89 

        resumo_html = f"""
        <div style="background-color: #87CEFA; padding: 15px; border-radius: 5px; color: black; font-family: sans-serif; border: 1px solid #1E90FF;">
            <div style="font-weight: bold; font-size: 16px; margin-bottom: 10px;">10. Valor da Assinatura Mensal: R$ {format_moeda(v_mensal_total)}</div>
            <div style="margin-left: 20px; font-size: 14px;">
                Assinatura do Orcas Baby: <span style="float: right;">19,90</span><br>
                {qtd_relatorios_totais} Resumo(s) Diário(s) via Whatsapp / E-mail: <span style="float: right;">{format_moeda(custo_relatorio_total)}</span><br>
                Usuário com {qtd_total_planos} Planos: <span style="float: right;">{format_moeda(add_planos_extra)}</span><br>
                {c24} Plano(s) com 24 meses: <span style="float: right;">0,00</span><br>
                {c36} Plano(s) com 36 meses: <span style="float: right;">{format_moeda(v_p36)}</span><br>
                {c48} Plano(s) com 48 meses: <span style="float: right;">{format_moeda(v_p48)}</span><br>
                {c60} Plano(s) com 60 meses: <span style="float: right;">{format_moeda(v_p60)}</span>
            </div>
            <div style="margin-top: 15px; font-weight: bold; border-top: 1px solid #5f9ea0; padding-top: 10px;">
                PROMOÇÃO:<br>
                Valor da Assinatura p/ 6 meses (-5%): R$ {format_moeda(v_6meses)}<br>
                Valor da Assinatura p/ 12 meses (-11%): R$ {format_moeda(v_12meses)}
            </div>
        </div>
        """
        col_l4_2.markdown(resumo_html, unsafe_allow_html=True)

        st.write("")

        opcoes_radio = ["Selecione uma opção...", "Mensal (Sem desconto)", "6 Meses (5% de desconto)", "12 Meses (11% de desconto)"]
        
        if "tipo_pagamento_selecionado" not in st.session_state:
            idx_padrao = 0
            if "Mensal" in tipo_renov_original: idx_padrao = 1
            elif "6 Meses" in tipo_renov_original: idx_padrao = 2
            elif "12 Meses" in tipo_renov_original: idx_padrao = 3
            st.session_state.tipo_pagamento_selecionado = opcoes_radio[idx_padrao]

        try:
            idx_radio = opcoes_radio.index(st.session_state.tipo_pagamento_selecionado)
        except ValueError:
            idx_radio = 0

        tipo_pagamento = st.radio(
            "11. Escolha o período de renovação:",
            opcoes_radio,
            index=idx_radio,
            horizontal=True, key=f"radio_pag_v{ver}"
        )
        st.session_state.tipo_pagamento_selecionado = tipo_pagamento

        meses_originais = 1
        if "6 Meses" in tipo_renov_original: meses_originais = 6
        elif "12 Meses" in tipo_renov_original: meses_originais = 12

        meses_novos = 1
        if "6 Meses" in tipo_pagamento: meses_novos = 6
        elif "12 Meses" in tipo_pagamento: meses_novos = 12

        valor_final_faturar = 0.00
        recalculo_expiracao = hoje.strftime('%Y-%m-%d')
        qtd_meses = 1
        label_desc = "Valor Padrão"

        if tipo_pagamento != "Selecione uma opção...":
            if "6 Meses" in tipo_pagamento:
                qtd_meses = 6
                v_custo_novo_periodo = v_6meses
                label_desc = "5% OFF"
                recalculo_expiracao = (hoje + relativedelta(months=6)).strftime('%Y-%m-%d')
            elif "12 Meses" in tipo_pagamento:
                qtd_meses = 12
                v_custo_novo_periodo = v_12meses
                label_desc = "11% OFF"
                recalculo_expiracao = (hoje + relativedelta(months=12)).strftime('%Y-%m-%d')
            else:
                qtd_meses = 1
                v_custo_novo_periodo = v_mensal_total
                label_desc = "Valor Padrão"
                recalculo_expiracao = (hoje + relativedelta(months=1)).strftime('%Y-%m-%d')

            if not vencimento_atual_str:
                vencimento_atual_str = st.session_state.get('vencimento', hoje.strftime('%Y-%m-%d'))
            
            try:
                venc_date = datetime.strptime(str(vencimento_atual_str)[:10], '%Y-%m-%d').date()
            except Exception:
                venc_date = hoje

            dias_restantes = (venc_date - hoje).days if venc_date > hoje else 0
            
            dias_totais_ciclo = 30
            if "6 Meses" in tipo_renov_original: dias_totais_ciclo = 180
            elif "12 Meses" in tipo_renov_original: dias_totais_ciclo = 365

            if valor_pago_real > 0:
                valor_diario_real = valor_pago_real / dias_totais_ciclo
                saldo_credito_usuario = max(dias_restantes * valor_diario_real, 0.0)
            else:
                saldo_credito_usuario = 0.00

            valor_final = v_custo_novo_periodo - saldo_credito_usuario

            if valor_final < 0 and "Mensal" in tipo_pagamento and dias_restantes > 30:
                saldo_perdido_exibir = abs(valor_final)
                diferenca_semestral_exibir = max(v_6meses - saldo_credito_usuario, 0.00)

                st.markdown(
                    f"""
                    <div style="color: #856404; background-color: #fff3cd; border-color: #ffeeba; padding: 15px; border: 1px solid transparent; border-radius: 4px; margin-top: 15px; margin-bottom: 15px; font-family: sans-serif; text-align: justify;">
                        ⚠️ <b>Aviso de Aproveitamento de Saldo:</b><br>
                        Como o sistema trabalha com opções fechadas, optando por uma renovação Mensal com créditos ativos, você terá este mês sem custos, mas perderá um saldo residual de <b>R$ {format_moeda(saldo_perdido_exibir)}</b>. Fazendo uma renovação Semestral, utiliza integralmente esse saldo e pagará apenas a diferença de <b>R$ {format_moeda(diferenca_semestral_exibir)}</b>.
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            if valor_final < 0:
                valor_final = 0.00

            valor_final_faturar = valor_final

        btn_col1, btn_col2 = st.columns(2)
        
        dados_p_salvamento = {
            "projeto_id": nome_plano_input, 
            "usuario_id": uid_gestao, 
            "saldo_inicial": parse_moeda(saldo_input),
            "data_ini": d_ini_g.strftime('%Y-%m-%d'), 
            "data_fim": st.session_state.tmp_fim_plano.strftime('%Y-%m-%d'),
            "zap_ativo": 1 if ativar_zap_atual else 0,
            "email_ativo": 1 if ativar_email_atual else 0
        }
        
        houve_upgrade_real = (v_mensal_total > ult_valor_mensal_lido) or (tipo_pagamento != "Selecione uma opção..." and meses_novos > meses_originais)

        if btn_col1.button("12. Salvar alterações ou Criar o novo Plano", use_container_width=True):
            if tipo_pagamento == "Selecione uma opção...":
                st.error("⚠️ Por favor, selecione um período de renovação abaixo para calcular se há valores a pagar antes de salvar.")
            
            elif v_mensal_total <= ult_valor_mensal_lido and meses_novos <= meses_originais:
                try:
                    res_p = supabase.table("config_projetos").select("id").eq("projeto_id", nome_plano_input).eq("usuario_id", uid_gestao).execute()
                    if res_p and hasattr(res_p, 'data') and res_p.data: 
                        dados_p_salvamento["id"] = res_p.data[0]["id"]
                    
                    supabase.table("config_projetos").upsert(dados_p_salvamento).execute()
                    supabase.table("usuarios").update({"ult_valor_mensal": float(v_mensal_total)}).eq("id", uid_gestao).execute()
                    supabase.table("lancamentos").delete().eq("projeto_id", nome_plano_input).eq("usuario_id", uid_gestao).gt("data", st.session_state.tmp_fim_plano.strftime('%Y-%m-%d')).execute()
                    
                    if 'tmp_fim_plano' in st.session_state: del st.session_state.tmp_fim_plano
                    if 'clicou_salvar_upgrade' in st.session_state: del st.session_state.clicou_salvar_upgrade
                    if 'tipo_pagamento_selecionado' in st.session_state: del st.session_state.tipo_pagamento_selecionado

                    st.session_state.projeto_ativo = nome_plano_input
                    st.session_state["nome_plano_input_key"] = nome_plano_input
                    st.session_state.msg_sucesso = "🎉 Alterações aplicadas com sucesso! Seu plano atual está coberto."
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar plano: {e}")
            else:
                st.session_state.clicou_salvar_upgrade = True
                st.rerun()

        if st.session_state.get('projeto_ativo'):
            if btn_col2.button("13. Excluir Plano", type="primary", use_container_width=True):
                st.session_state.confirmar_exclusao_plano = True

        if st.session_state.get('confirmar_exclusao_plano', False):
            st.error(f"14. Deseja mesmo excluir o plano {st.session_state.projeto_ativo}?")
            ce1, ce2 = st.columns(2)
            if ce1.button("CONFIRMAR EXCLUSÃO"):
                supabase.table("lancamentos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid_gestao).execute()
                supabase.table("config_projetos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid_gestao).execute()
                st.session_state.projeto_ativo = None
                if "nome_plano_input_key" in st.session_state: del st.session_state.nome_plano_input_key
                st.session_state.confirmar_exclusao_plano = False
                st.rerun()
            if ce2.button("CANCELAR"):
                st.session_state.confirmar_exclusao_plano = False
                st.rerun()

        # --- SEÇÃO DE FECHAMENTO FINANCEIRO ---
        if st.session_state.get("clicou_salvar_upgrade", False) and houve_upgrade_real:
            st.markdown(
                f"""
                <div style="color: #856404; background-color: #fff3cd; border-color: #ffeeba; padding: 15px; border: 1px solid transparent; border-radius: 4px; margin-top: 15px; margin-bottom: 15px; font-family: sans-serif;">
                    ⚠️ <b>Esta alteração altera o valor ou o período da sua licença ({tipo_renov_original} ➡️ {tipo_pagamento}).</b> Utilize o bloco de fechamento abaixo para concluir o pagamento de upgrade.
                </div>
                """, 
                unsafe_allow_html=True
            )

            st.write("")
            st.subheader("💳 20. Finalizar Assinatura")

            st.write("")
            cupom_in = st.text_input("21. Possui um Cupom de Desconto?", key=f"cp_gest_v{ver}").upper()
            desc_extra = 0.0
            is_cupom_100 = False

            if cupom_in:
                try:
                    res_c = supabase.table("cupons").select("*").eq("codigo", cupom_in).eq("ativo", True).execute()
                    if res_c.data:
                        d = res_c.data[0]
                        v_p = float(d.get('percentual_desconto', 0) or 0)
                        v_a = float(d.get('valor_desconto', 0) or 0)
                        
                        if v_p >= 100.0:
                            is_cupom_100 = True
                            desc_extra = valor_final_faturar
                        else:
                            desc_extra = valor_final_faturar * (v_p / 100) if v_p > 0 else v_a
                        
                        if not is_cupom_100:
                            st.success("✅ Cupom aplicado!")
                    else:
                        st.error("❌ Cupom inválido.")
                except: pass

            valor_final_faturar = max(valor_final_faturar - desc_extra, 0.00)
            if valor_final_faturar == 0.00:
                is_cupom_100 = True

            col_res1, col_res2 = st.columns([2, 1])
            with col_res1:
                if is_cupom_100:
                    st.markdown(
                        """
                        <div style="color: #155724; background-color: #d4edda; border-color: #c3e6cb; padding: 12px; border-radius: 4px; font-weight: bold; font-family: sans-serif;">
                            🎉 Após a aplicação do Cupom, o sistema verificou que você não tem nenhum valor a pagar!
                        </div>
                        """, unsafe_allow_html=True
                    )
                else:
                    st.write(f"**Total a pagar:** :green[R$ {valor_final_faturar:.2f}] ({label_desc})")
                
                try:
                    venc_proposto_f = datetime.strptime(recalculo_expiracao, '%Y-%m-%d').strftime('%d/%m/%Y')
                    st.write(f"*(Sua licença estenderá para a data: {venc_proposto_f})*")
                except: pass
            
            with col_res2:
                if is_cupom_100:
                    if st.button("✅ 23. CONCLUIR ASSINATURA GRÁTIS", use_container_width=True, type="primary"):
                        try:
                            res_p = supabase.table("config_projetos").select("id").eq("projeto_id", nome_plano_input).eq("usuario_id", uid_gestao).execute()
                            if res_p and hasattr(res_p, 'data') and res_p.data: 
                                dados_p_salvamento["id"] = res_p.data[0]["id"]
                            
                            supabase.table("config_projetos").upsert(dados_p_salvamento).execute()
                            
                            supabase.table("usuarios").update({
                                "vencimento": recalculo_expiracao,
                                "tipo_renovacao": str(tipo_pagamento), 
                                "valor_pago": 0.00,
                                "data_ult_assinat": hoje.strftime('%Y-%m-%d'),
                                "ult_valor_mensal": float(v_mensal_total)
                            }).eq("id", uid_gestao).execute()
                            
                            if 'tmp_fim_plano' in st.session_state: del st.session_state.tmp_fim_plano
                            if 'clicou_salvar_upgrade' in st.session_state: del st.session_state.clicou_salvar_upgrade
                            if 'tipo_pagamento_selecionado' in st.session_state: del st.session_state.tipo_pagamento_selecionado

                            st.session_state.projeto_ativo = nome_plano_input
                            st.session_state["nome_plano_input_key"] = nome_plano_input
                            st.session_state.msg_sucesso = "🎉 Assinatura atualizada com sucesso via Cupom!"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao processar validação do cupom gratuito: {e}")
                else:
                    if st.button("🚀 22. GERAR LINK DE PAGAMENTO", use_container_width=True):
                        with st.spinner("Preparando fatura segura..."):
                            plano_para_vincular = nome_plano_input.strip() if nome_plano_input else "Plano"
                            import orcas_v01_pagamentos as pag
                            email_user = st.session_state.get('usuario_email', "cliente@email.com")

                            try:
                                link, pref_id = pag.criar_link_final(
                                    uid_gestao, 
                                    valor_final_faturar, 
                                    f"Assinatura ORCAS - {qtd_meses} Meses",
                                    email_user,
                                    qtd_meses,
                                    None
                                )
                            except Exception as e:
                                st.error(f"Erro ao gerar link no gateway: {e}")
                                link, pref_id = None, None
                            
                            if link:
                                st.session_state.url_ativa = link
                                st.session_state.pref_id_ativa = pref_id if pref_id else ID_USUARIO_LOGADO
                                st.session_state.meses_comprados = qtd_meses
                                
                                try:
                                    id_filtro = str(ID_USUARIO_LOGADO).strip()
                                    supabase.table("pagamentos_temp").delete().eq("usuario_id", id_filtro).execute()
                                
                                    supabase.table("pagamentos_temp").insert({
                                        "usuario_id": id_filtro,
                                        "pref_id": str(st.session_state.pref_id_ativa),
                                        "valor": float(valor_final_faturar),
                                        "status": "aguardando",
                                        "projeto_id": plano_para_vincular,
                                        "data_ini": dados_p_salvamento.get("data_ini"),
                                        "data_fim": dados_p_salvamento.get("data_fim"),
                                        "zap_ativo": bool(ativar_zap_atual),
                                        "email_ativo": int(1 if ativar_email_atual else 0),
                                        "tipo_renovacao": str(tipo_pagamento),
                                        "ult_valor_mensal": float(v_mensal_total)
                                    }).execute()
                                
                                    st.toast("Link gerado com sucesso!")
                                except Exception as e:
                                    st.error(f"Erro ao registrar transação temporária: {e}")
            
            if "url_ativa" in st.session_state and not is_cupom_100:
                st.link_button("🔵 30. PAGAMENTO - IR P/ MERCADO PAGO", st.session_state.url_ativa, use_container_width=True)
        
        elif tipo_pagamento != "Selecione uma opção..." and not houve_upgrade_real:
            st.info("ℹ️ Este plano está coberto pela sua assinatura atual. Não há valores adicionais a pagar.")
            
    else:
        st.info("💡 Selecione um plano acima para editar ou digite um novo nome para configuração.")

    st.markdown("""
    <div style="font-size: 12px; color: #333; margin-top: 20px; text-align: justify; line-height: 1.6; border-top: 1px solid #eee; padding-top: 10px;">
    Sua Assinatura ORCAS BABY mensal custa R$ 19,90 e contempla 2 Planos de 24 meses cada um, mas se você quiser ou necessitar, é possível aumentar o período de um Plano em blocos adicionais de 12 meses tendo um acréscimo de R$ 6,40 para cada 12 meses adicionais. Para aumentar o número de Planos (Padrão - 24 meses), o valor é de R$ 12,80 por Plano adicional. Para receber um Resumo Diário das análises e pendências como, o que preciso pagar e receber hoje, o que ainda está em aberto, quanto já gastei de supermercado até hoje, quanto já gastei nessa reforma, etc de seu Plano via Whatsapp ou E-mail terá um acréscimo de R$ 9,85 por Plano.
    </div>
    """, unsafe_allow_html=True)