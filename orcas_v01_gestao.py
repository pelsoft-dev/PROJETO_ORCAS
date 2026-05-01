import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def exibir_gestao(supabase, ID_USUARIO_LOGADO, projs, d_ini_db, d_fim_db, s_db, format_moeda, parse_moeda, security):
    """
    Sub-rotina da Tela Gestão - Controle de Planos, Saldos e Assinatura.
    """
    st.markdown('<div class="titulo-tela">Gestão de Planos e Assinaturas</div>', unsafe_allow_html=True)
    
    hoje = datetime.now().date()
    uid_gestao = ID_USUARIO_LOGADO

    v_mensal_total = 0.0

    # --- REGRAS DE NEGÓCIO CENTRALIZADAS ---
    DESC_6_MESES = 0.05  # 5%
    DESC_12_MESES = 0.11 # 11%

    if st.session_state.get('msg_sucesso'):
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    col_l1_1, col_l1_2 = st.columns(2)
    lista_gestao = [""] + projs
    
    plano_sel = col_l1_1.selectbox("Selecione um Plano já existente:", lista_gestao)
    
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
        
        # Leitura segura para evitar erro de coluna inexistente antes do ALTER TABLE
        res_cfg_plano = supabase.table("config_projetos").select("*").eq("projeto_id", nome_plano_input).eq("usuario_id", uid_gestao).execute()
        zap_plano_db = res_cfg_plano.data[0].get('zap_ativo', 0) if res_cfg_plano.data else 0
        email_plano_db = res_cfg_plano.data[0].get('email_ativo', 0) if res_cfg_plano.data else 0
        
        with col_l4_1:
            st.write("") 
            st.write("") 
            ativar_zap_atual = st.checkbox("Adicionar o Resumo Diário ORCAS via Whatsapp", value=(zap_plano_db == 1))
            ativar_email_atual = st.checkbox("Adicionar o Resumo Diário ORCAS via E-mail", value=(email_plano_db == 1))
        
        res_all = supabase.table("config_projetos").select("*").eq("usuario_id", uid_gestao).execute()
        dados_db = res_all.data if res_all.data else []
        
        planos_consolidar = {}
        relatorios_consolidar = {}
        
        for p in dados_db:
            d1 = datetime.strptime(p['data_ini'], '%Y-%m-%d').date()
            d2 = datetime.strptime(p['data_fim'], '%Y-%m-%d').date()
            duracao = (d2.year - d1.year) * 12 + (d2.month - d1.month) + 1
            planos_consolidar[p['projeto_id']] = duracao
            rel_ativo = 1 if (p.get('zap_ativo', 0) == 1 or p.get('email_ativo', 0) == 1) else 0
            relatorios_consolidar[p['projeto_id']] = rel_ativo

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

        # TÍTULO ALTERADO CONFORME SOLICITADO
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

        st.divider()

        btn_col1, btn_col2 = st.columns(2)
        if btn_col1.button("Salvar alterações ou Criar o novo Plano", use_container_width=True):
            dados_p = {
                "projeto_id": nome_plano_input, 
                "usuario_id": uid_gestao, 
                "saldo_inicial": parse_moeda(saldo_input),
                "data_ini": d_ini_g.strftime('%Y-%m-%d'), 
                "data_fim": st.session_state.tmp_fim_plano.strftime('%Y-%m-%d'),
                "zap_ativo": 1 if ativar_zap_atual else 0,
                "email_ativo": 1 if ativar_email_atual else 0
            }
            res_p = supabase.table("config_projetos").select("id").eq("projeto_id", nome_plano_input).eq("usuario_id", uid_gestao).execute()
            if res_p.data: dados_p["id"] = res_p.data[0]["id"]
            
            supabase.table("config_projetos").upsert(dados_p).execute()
            # --- NOVO BLOCO QUE ENTRA AQUI ---
            # Deleta lançamentos com data MAIOR (gt) que a nova data de término
            supabase.table("lancamentos")\
                .delete()\
                .eq("projeto_id", nome_plano_input)\
                .eq("usuario_id", uid_gestao)\
                .gt("data", st.session_state.tmp_fim_plano.strftime('%Y-%m-%d'))\
                .execute()
            # -------------------------------------------------------
            if 'tmp_fim_plano' in st.session_state: del st.session_state.tmp_fim_plano
            st.session_state.projeto_ativo = nome_plano_input
            st.session_state.msg_sucesso = "Configurações salvas com sucesso!"
            st.rerun()

        if st.session_state.get('projeto_ativo'):
            if btn_col2.button("Excluir Plano", type="primary", use_container_width=True):
                st.session_state.confirmar_exclusao_plano = True

        # if st.button("Ir para Pagamentos", use_container_width=True, type="secondary"):
        #    st.session_state.escolha = "💳 Pagamentos"
        #    st.rerun()

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
    else:
        st.info("Por favor, selecione um plano existente ou digite um nome para iniciar a configuração.")

# --- BLOCO DE SELEÇÃO DE PAGAMENTO ---
    st.write("---")
    st.subheader("💳 Finalizar Assinatura")
    
    tipo_pagamento = st.radio(
        "Escolha o período de renovação:",
        ["Mensal (Sem desconto)", "6 Meses (5% de desconto)", "12 Meses (11% de desconto)"],
        horizontal=True
    )

    # Cálculos de valores (v_mensal_total deve estar definido antes no seu código)
    if "6 Meses" in tipo_pagamento:
        qtd_meses = 6
        valor_base = (v_mensal_total * 6) * (1 - DESC_6_MESES)
    elif "12 Meses" in tipo_pagamento:
        qtd_meses = 12
        valor_base = (v_mensal_total * 12) * (1 - DESC_12_MESES)
    else:
        qtd_meses = 1
        valor_base = v_mensal_total

    # Sistema de Cupom
    st.write("")
    cupom_input = st.text_input("Possui um Cupom?", key="cp_input_gestao").upper()
    desc_extra = 0.0

    if cupom_input:
        try:
            res_c = supabase.table("cupons").select("*").eq("codigo", cupom_input).eq("ativo", True).execute()
            if res_c.data:
                d = res_c.data[0]
                v_p = float(d.get('percentual_desconto', 0) or 0)
                v_a = float(d.get('valor_desconto', 0) or 0)
                desc_extra = valor_base * (v_p/100) if v_p > 0 else v_a
                st.success("✅ Cupom aplicado!")
            else:
                st.error("❌ Cupom inválido.")
        except Exception:
            pass

    valor_final = max(valor_base - desc_extra, 1.00)

    # --- FUNÇÃO DE PAGAMENTO INTEGRADA (Para evitar erro de importação) ---
    def gerar_checkout_mp(user_id, valor, desc):
        import mercadopago
        try:
            sdk = mercadopago.SDK(st.secrets["MP_ACCESS_TOKEN"])
            preference_data = {
                "items": [{"title": desc, "quantity": 1, "unit_price": float(valor)}],
                "external_reference": str(user_id),
                "payment_methods": {
                    "excluded_payment_methods": [{"id": "consumer_credits"}],
                    "installments": 1 
                },
                "auto_return": "approved",
            }
            res = sdk.preference().create(preference_data)
            return res["response"].get("init_point")
        except Exception as e:
            st.error(f"Erro técnico: {e}")
            return None

    col_res1, col_res2 = st.columns([2, 1])
    with col_res1:
        st.write(f"**Total a pagar:** :green[R$ {valor_final:.2f}]")
    
    with col_res2:
        # FORÇA A COR VERDE NO BOTÃO
        st.markdown("""
            <style>
            div.stButton > button:first-child { 
                background-color: #28a745 !important; 
                color: white !important; 
                border-radius: 8px;
            }
            </style>
        """, unsafe_allow_html=True)

        # BOTÃO 1: VERDE - GERA O LINK
        if st.button("🚀 PAGAR AGORA", use_container_width=True):
            descricao_venda = f"Assinatura ORCAS - {qtd_meses} Meses"
            link = gerar_checkout_mp(ID_USUARIO_LOGADO, valor_final, descricao_venda)
            if link:
                st.session_state.url_ativa = link
            else:
                st.error("Não foi possível gerar o link. Verifique o Access Token.")

        # BOTÃO 2: AZUL - SÓ APARECE SE O LINK FOR GERADO
        if "url_ativa" in st.session_state:
            st.markdown(f'''
                <a href="{st.session_state.url_ativa}" target="_blank" style="text-decoration: none;">
                    <div style="background-color: #009EE3; color: white; padding: 12px; border-radius: 8px; font-weight: bold; text-align: center; margin-top: 10px; box-shadow: 0px 4px 10px rgba(0,0,0,0.1);">
                        CLIQUE AQUI PARA ABRIR O CHECKOUT ➔
                    </div>
                </a>
            ''', unsafe_allow_html=True)

    # Rodapé informativo fixo
    st.markdown("""
    <div style="font-size: 12px; color: #333; margin-top: 20px; text-align: justify; line-height: 1.6; border-top: 1px solid #eee; padding-top: 10px;">
    Sua Assinatura ORCAS BABY mensal custa R$ 19,90 e contempla 2 Planos de 24 meses cada um...
    </div>
    """, unsafe_allow_html=True)