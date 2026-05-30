import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta

def exibir_gestao(supabase, ID_USUARIO_LOGADO, projs, d_ini_db, d_fim_db, s_db, format_moeda, parse_moeda, security):
    """
    Sub-rotina da Tela Gestão - Controle de Planos, Saldos e Assinatura.
    Lógica de proteção: salvamento na tabela oficial só ocorre direto se o valor a pagar for R$ 0,00.
    """
    
    # --- 1. TRATAMENTO DO PERFIL DO UTILIZADOR E VALOR PAGO REAL ---
    tipo_renov_original = "6 Meses"
    vencimento_atual_str = None
    valor_pago_real = 0.00
    data_ult_assinat_real = None
    
    try:
        res_user_master = supabase.table("usuarios").select("*").eq("id", ID_USUARIO_LOGADO).execute()
        if res_user_master and hasattr(res_user_master, 'data') and len(res_user_master.data) > 0:
            dados_usuario = res_user_master.data[0]
            vencimento_atual_str = dados_usuario.get('vencimento')
            
            valor_pago_real = float(dados_usuario.get('valor_pago') or 0.00)
            data_pag_aux = dados_usuario.get('data_ult_assinat') or dados_usuario.get('criado_em')
            if data_pag_aux:
                data_ult_assinat_real = datetime.strptime(str(data_pag_aux)[:10], '%Y-%m-%d').date()
            
            val_db = dados_usuario.get('tipo_renovacao')
            if val_db is not None:
                tipo_renov_original = str(val_db).strip()
    except Exception:
        tipo_renov_original = "6 Meses"

    if not tipo_renov_original:
        tipo_renov_original = "6 Meses"

    st.markdown('<div class="titulo-tela">Gestão de Planos e Assinaturas</div>', unsafe_allow_html=True)
    
    hoje = datetime.now().date()
    uid_gestao = ID_USUARIO_LOGADO

    if st.session_state.get('msg_sucesso'):
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    col_l1_1, col_l1_2 = st.columns(2)
    lista_gestao = [""] + projs
    
    plano_sel = col_l1_1.selectbox("Selecione um Plano já existente:", lista_gestao, key="sb_plano_gestao_unique")
    
    if plano_sel != "" and plano_sel != st.session_state.get('projeto_ativo'):
        st.session_state.projeto_ativo = plano_sel
        st.session_state.escolha = "⚙️ Gestão" 
        if 'tmp_fim_plano' in st.session_state: del st.session_state.tmp_fim_plano
        st.rerun()

    nome_plano_input = col_l1_2.text_input(
        "Nome do Plano carregado ou Nome para criação de um novo Plano", 
        value=st.session_state.projeto_ativo if st.session_state.projeto_ativo else ""
    )

    if nome_plano_input and nome_plano_input.strip() != "":
        col_l2_1, col_l2_2 = st.columns(2)
        
        data_inicio_padrao = d_ini_db if d_ini_db else hoje.replace(day=1)
        if not d_fim_db:
            data_fim_padrao = (data_inicio_padrao + relativedelta(months=23)).replace(day=1) + relativedelta(months=1, days=-1)
        else:
            data_fim_padrao = d_fim_db

        if 'tmp_fim_plano' not in st.session_state:
            st.session_state.tmp_fim_plano = data_fim_padrao

        d_ini_g = col_l2_1.date_input("Data de Início:", value=data_inicio_padrao, format="DD/MM/YYYY")
        
        col_fim, col_btn_per = col_l2_2.columns(2)
        
        diff_edit = relativedelta(st.session_state.tmp_fim_plano, d_ini_g)
        meses_atuais = (diff_edit.years * 12) + diff_edit.months + 1
        if meses_atuais not in [24, 36, 48, 60]:
            meses_atuais = 24

        with col_btn_per:
            periodo_slider = st.select_slider(
                "Aumentar Período (em 12 meses)",
                options=[24, 36, 48, 60],
                value=meses_atuais
            )
            nova_data_fim = (d_ini_g + relativedelta(months=periodo_slider - 1))
            nova_data_fim = (nova_data_fim.replace(day=1) + relativedelta(months=1, days=-1))
            st.session_state.tmp_fim_plano = nova_data_fim

        d_fim_g = col_fim.date_input("Data de Término:", value=st.session_state.tmp_fim_plano, format="DD/MM/YYYY", disabled=True)

        col_l3_1, col_l3_2 = st.columns(2)
        valor_saldo_exibir = format_moeda(s_db) if s_db is not None else "0,00"
        saldo_input = col_l3_1.text_input("Saldo Inicial:", value=valor_saldo_exibir)
        
        meses_total_edit = (st.session_state.tmp_fim_plano.year - d_ini_g.year) * 12 + (st.session_state.tmp_fim_plano.month - d_ini_g.month) + 1
        col_l3_2.text_input("Período do Plano:", value=f"{meses_total_edit} meses", disabled=True)

        col_l4_1, col_l4_2 = st.columns(2)
        
        res_cfg_plano = supabase.table("config_projetos").select("*").eq("projeto_id", nome_plano_input).eq("usuario_id", uid_gestao).execute()
        
        zap_plano_db = res_cfg_plano.data[0].get('zap_ativo', 0) if res_cfg_plano.data else 0
        email_plano_db = res_cfg_plano.data[0].get('email_ativo', 0) if res_cfg_plano.data else 0
        meses_originais_db = 24
        if res_cfg_plano.data:
            d1_orig = datetime.strptime(res_cfg_plano.data[0]['data_ini'], '%Y-%m-%d').date()
            d2_orig = datetime.strptime(res_cfg_plano.data[0]['data_fim'], '%Y-%m-%d').date()
            meses_originais_db = (d2_orig.year - d1_orig.year) * 12 + (d2_orig.month - d1_orig.month) + 1
        
        with col_l4_1:
            st.write("") 
            st.write("") 
            ativar_zap_atual = st.checkbox("Adicionar o Resumo Diário ORCAS via Whatsapp", value=(zap_plano_db == 1))
            ativar_email_atual = st.checkbox("Adicionar o Resumo Diário ORCAS via E-mail", value=(email_plano_db == 1))
        
        # --- 2. POSICIONAMENTO E CORREÇÃO DOS DICIONÁRIOS (EVITA NAMEERROR) ---
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

        # --- QUADRO RESUMO AZUL ---
        resumo_html = f"""
        <div style="background-color: #87CEFA; padding: 15px; border-radius: 5px; color: black; font-family: sans-serif; border: 1px solid #1E90FF;">
            <div style="font-weight: bold; font-size: 16px; margin-bottom: 10px;">Valor da Assinatura Mensal: R$ {format_moeda(v_mensal_total)}</div>
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

        tipo_pagamento = st.radio(
            "Escolha o período de renovação:",
            ["Selecione uma opção...", "Mensal (Sem desconto)", "6 Meses (5% de desconto)", "12 Meses (11% de desconto)"],
            horizontal=True, key="radio_pag_final_v10"
        )

        # --- 3. CRÉDITOS E PROTEÇÃO DE CONVERSÃO DE DATAS (EVITA TYPEERROR) ---
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
            
            # Garante que dias_totais_ciclo nunca seja zero ou cause divisão por zero
            dias_totais_ciclo = 180
            if data_ult_assinat_real and venc_date > data_ult_assinat_real:
                dias_totais_ciclo = (venc_date - data_ult_assinat_real).days
            else:
                if "6 Meses" in tipo_renov_original: dias_totais_ciclo = 180
                elif "12 Meses" in tipo_renov_original: dias_totais_ciclo = 365
                else: dias_totais_ciclo = 30
            
            if dias_totais_ciclo <= 0:
                dias_totais_ciclo = 30

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

        # --- VERIFICAÇÃO DE MUDANÇA DE PARÂMETROS ---
        houve_mudanca_parametros = False
        if res_cfg_plano.data:
            if (meses_total_edit != meses_originais_db or 
                (1 if ativar_zap_atual else 0) != zap_plano_db or 
                (1 if ativar_email_atual else 0) != email_plano_db):
                houve_mudanca_parametros = True
        elif nome_plano_input.strip() != "":
            houve_mudanca_parametros = True

        if houve_mudanca_parametros:
            st.markdown(
                f"""
                <div style="color: #1E3A8A; background-color: #EBF5FF; border-color: #BFDBFE; padding: 12px; border: 1px solid transparent; border-radius: 4px; margin-top: 5px; margin-bottom: 15px; font-family: sans-serif;">
                    💡 Você alterou a configuração da sua Licença, salve as alterações e verifique abaixo se existe valor a pagar.
                </div>
                """, 
                unsafe_allow_html=True
            )

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

        # --- COMPORTAMENTO DOS BOTÕES ---
        if btn_col1.button("Salvar alterações ou Criar o novo Plano", use_container_width=True):
            if tipo_pagamento == "Selecione uma opção...":
                st.error("⚠️ Por favor, selecione um período de renovação abaixo para calcular se há valores a pagar antes de salvar.")
            elif valor_final_faturar <= 0:
                try:
                    res_p = supabase.table("config_projetos").select("id").eq("projeto_id", nome_plano_input).eq("usuario_id", uid_gestao).execute()
                    # CORREÇÃO DO APIERROR: Remove ou atualiza o ID dinamicamente apenas se o registro de fato existir
                    if res_p and hasattr(res_p, 'data') and res_p.data: 
                        dados_p_salvamento["id"] = res_p.data[0]["id"]
                    
                    supabase.table("config_projetos").upsert(dados_p_salvamento).execute()
                    supabase.table("lancamentos").delete().eq("projeto_id", nome_plano_input).eq("usuario_id", uid_gestao).gt("data", st.session_state.tmp_fim_plano.strftime('%Y-%m-%d')).execute()
                    
                    if 'tmp_fim_plano' in st.session_state: del st.session_state.tmp_fim_plano
                    st.session_state.projeto_ativo = nome_plano_input
                    st.session_state.msg_sucesso = "🎉 Alterações aplicadas com sucesso! Seus créditos cobriram a mudança (Custo: R$ 0,00)."
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar plano: {e}")
            else:
                st.warning("⚠️ Esta alteração altera o valor da sua licença. Utilize o botão 'GERAR LINK DE PAGAMENTO' abaixo para concluir.")

        if st.session_state.get('projeto_ativo'):
            if btn_col2.button("Excluir Plano", type="primary", use_container_width=True):
                st.session_state.confirmar_exclusao_plano = True

        if st.session_state.get('confirmar_exclusao_plano', False):
            st.error(f"Deseja mesmo excluir o plano {st.session_state.projeto_ativo}?")
            ce1, ce2 = st.columns(2)
            if ce1.button("CONFIRMAR EXCLUSÃO"):
                supabase.table("lancamentos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid_gestao).execute()
                supabase.table("config_projetos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid_gestao).execute()
                st.session_state.projeto_ativo = None
                st.session_state.confirmar_exclusao_plano = False
                st.rerun()
            if ce2.button("CANCELAR"):
                st.session_state.confirmar_exclusao_plano = False
                st.rerun()

        st.write("")
        st.subheader("💳 Finalizar Assinatura")

        if tipo_pagamento != "Selecione uma opção...":
            dados_p_salvamento["tipo_renovacao"] = tipo_pagamento

            st.write("")
            cupom_in = st.text_input("Possui um Cupom de Desconto?", key="cp_gest_final_v7").upper()
            desc_extra = 0.0
            if cupom_in:
                try:
                    res_c = supabase.table("cupons").select("*").eq("codigo", cupom_in).eq("ativo", True).execute()
                    if res_c.data:
                        d = res_c.data[0]
                        v_p = float(d.get('percentual_desconto', 0) or 0)
                        v_a = float(d.get('valor_desconto', 0) or 0)
                        desc_extra = valor_final_faturar * (v_p / 100) if v_p > 0 else v_a
                        st.success("✅ Cupom aplicado!")
                    else:
                        st.error("❌ Cupom inválido.")
                except: pass

            valor_final_faturar = max(valor_final_faturar - desc_extra, 0.00)

            col_res1, col_res2 = st.columns([2, 1])
            with col_res1:
                if valor_final_faturar <= 0:
                    st.write(f"**Total a pagar:** :green[R$ 0,00] (Crédito residual cobre as alterações)")
                    try:
                        venc_f = datetime.strptime(str(vencimento_atual_str)[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
                        st.write(f"*(Sua validade atual de {venc_f} foi mantida intacta)*")
                    except: pass
                else:
                    st.write(f"**Total a pagar:** :green[R$ {valor_final_faturar:.2f}] ({label_desc})")
                    try:
                        venc_proposto_f = datetime.strptime(recalculo_expiracao, '%Y-%m-%d').strftime('%d/%m/%Y')
                        st.write(f"*(Sua licença estenderá para a data: {venc_proposto_f})*")
                    except: pass
            
            with col_res2:
                if valor_final_faturar > 0:
                    if st.button("🚀 GERAR LINK DE PAGAMENTO", use_container_width=True):
                        with st.spinner("Preparando fatura segura..."):
                            plano_para_vincular = nome_plano_input.strip() if nome_plano_input else None
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
                                    # CORREÇÃO CRÍTICA DO SCHEMA 'pagamentos_temp': 
                                    # Removidos campos inexistentes que quebravam o cache do PostgREST.
                                    supabase.table("pagamentos_temp").upsert({
                                        "usuario_id": ID_USUARIO_LOGADO,
                                        "pref_id": str(st.session_state.pref_id_ativa),
                                        "valor": float(valor_final_faturar),
                                        "status": "aguardando",
                                        "projeto_id": plano_para_vincular
                                    }).execute()
                                    st.toast("Link gerado com sucesso!")
                                except Exception as e:
                                    st.error(f"Erro ao registrar transação temporária: {e}")
            
            if "url_ativa" in st.session_state and valor_final_faturar > 0:
                st.link_button("🔵 PAGAMENTO - IR P/ MERCADO PAGO", st.session_state.url_ativa, use_container_width=True)
        else:
            st.info("ℹ️ Escolha um período de renovação acima para prosseguir com a finalização da assinatura.")
    else:
        st.info("💡 Selecione um plano acima para editar ou digite um novo nome para configuração.")

    st.markdown("""
    <div style="font-size: 12px; color: #333; margin-top: 20px; text-align: justify; line-height: 1.6; border-top: 1px solid #eee; padding-top: 10px;">
    Sua Assinatura ORCAS BABY mensal custa R$ 19,90 e contempla 2 Planos de 24 meses cada um, mas se você quiser ou necessitar, é possível aumentar o período de um Plano em blocos adicionais de 12 meses tendo um acréscimo de R$ 6,40 para cada 12 meses adicionais. Para aumentar o número de Planos (Padrão - 24 meses), o valor é de R$ 12,80 por Plano adicional. Para receber um Resumo Diário das análises e pendências como, o que preciso pagar e receber hoje, o que ainda está em aberto, quanto já gastei de supermercado até hoje, quanto já gastei nessa reforma, etc de seu Plano via Whatsapp ou E-mail terá um acréscimo de R$ 9,85 por Plano.
    </div>
    """, unsafe_allow_html=True)