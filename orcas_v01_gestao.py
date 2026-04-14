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

    if st.session_state.get('msg_sucesso'):
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    col_l1_1, col_l1_2 = st.columns(2)
    lista_gestao = [""] + projs
    
    plano_sel = col_l1_1.selectbox("Selecione um Plano já existente:", lista_gestao)
    
    if plano_sel != "" and plano_sel != st.session_state.get('projeto_ativo'):
        st.session_state.projeto_ativo = plano_sel
        st.session_state.escolha = "⚙️ Gestão" 
        # Limpar datas temporárias para carregar do banco no próximo ciclo
        if 'tmp_fim_plano' in st.session_state: del st.session_state.tmp_fim_plano
        st.rerun()

    nome_plano_input = col_l1_2.text_input(
        "Nome do Plano carregado ou Nome para criação de um novo Plano", 
        value=st.session_state.projeto_ativo if st.session_state.projeto_ativo else ""
    )

    if nome_plano_input and nome_plano_input.strip() != "":
        col_l2_1, col_l2_2 = st.columns(2)
        
        # (1) Lógica de Início e Término
        data_inicio_padrao = d_ini_db if d_ini_db else hoje.replace(day=1)
        if not d_fim_db:
            data_fim_padrao = (data_inicio_padrao + relativedelta(months=23)).replace(day=1) + relativedelta(months=1, days=-1)
        else:
            data_fim_padrao = d_fim_db

        if 'tmp_fim_plano' not in st.session_state:
            st.session_state.tmp_fim_plano = data_fim_padrao

        d_ini_g = col_l2_1.date_input("Data de Início:", value=data_inicio_padrao, format="DD/MM/YYYY")
        
        col_fim, col_btn_per = col_l2_2.columns(2)
        
        # Cálculo da duração para o Slider baseado na data que está na tela
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
            
            # Recalcula a data de término sempre que o slider mudar
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
        
        # Checkbox do Zap e Email do plano atual conforme anexo
        res_cfg_plano = supabase.table("config_projetos").select("zap_ativo, email_ativo").eq("projeto_id", nome_plano_input).eq("usuario_id", uid_gestao).execute()
        zap_plano_db = res_cfg_plano.data[0]['zap_ativo'] if res_cfg_plano.data else 0
        email_plano_db = res_cfg_plano.data[0].get('email_ativo', 0) if res_cfg_plano.data else 0
        
        with col_l4_1:
            st.write("") # Espaçador
            st.write("") 
            ativar_zap_atual = st.checkbox("Adicionar o Relatório Diário ORCAS via Whatsapp", value=(zap_plano_db == 1))
            ativar_email_atual = st.checkbox("Adicionar o Relatório Diário ORCAS via E-mail", value=(email_plano_db == 1))
        
        # --- LÓGICA DE CONSOLIDAÇÃO LENDO TODOS OS PLANOS DO BANCO ---
        res_all = supabase.table("config_projetos").select("projeto_id, data_ini, data_fim, zap_ativo, email_ativo").eq("usuario_id", uid_gestao).execute()
        dados_db = res_all.data if res_all.data else []
        
        planos_consolidar = {}
        relatorios_consolidar = {}
        
        # Carrega o que já existe no banco
        for p in dados_db:
            d1 = datetime.strptime(p['data_ini'], '%Y-%m-%d').date()
            d2 = datetime.strptime(p['data_fim'], '%Y-%m-%d').date()
            duracao = (d2.year - d1.year) * 12 + (d2.month - d1.month) + 1
            planos_consolidar[p['projeto_id']] = duracao
            # Se qualquer um estiver ativo, conta como 1 relatório cobrado
            rel_ativo = 1 if (p.get('zap_ativo', 0) == 1 or p.get('email_ativo', 0) == 1) else 0
            relatorios_consolidar[p['projeto_id']] = rel_ativo

        # Sobrescreve com o que está na tela (antes de salvar) para refletir a mudança imediata no quadro azul
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
            <div style="font-weight: bold; font-size: 16px; margin-bottom: 10px;">Valor da Assinatura Mensal: R$ {format_moeda(v_mensal_total)}</div>
            <div style="margin-left: 20px; font-size: 14px;">
                Assinatura do Orcas Baby: <span style="float: right;">19,90</span><br>
                {qtd_relatorios_totais} Relatório(s) Diário(s) via Whatsapp: <span style="float: right;">{format_moeda(custo_relatorio_total)}</span><br>
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
            
            # Limpar temporários para forçar recarga correta
            if 'tmp_fim_plano' in st.session_state: del st.session_state.tmp_fim_plano
            st.session_state.projeto_ativo = nome_plano_input
            st.session_state.msg_sucesso = "Configurações salvas com sucesso!"
            st.rerun()

        if st.session_state.get('projeto_ativo'):
            if btn_col2.button("Excluir Plano", type="primary", use_container_width=True):
                st.session_state.confirmar_exclusao_plano = True

        if st.button("Ir para Pagamentos", use_container_width=True, type="secondary"):
            st.session_state.escolha = "💳 Pagamentos"
            st.rerun()

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

    st.markdown("""
    <div style="font-size: 12px; color: #333; margin-top: 20px; text-align: justify; line-height: 1.6;">
    Sua Assinatura ORCAS BABY mensal custa R$ 19,90 e contempla 2 Planos de 24 meses cada um, mas se você quiser ou necessitar, é possível aumentar o período de um Plano em blocos adicionais de 12 meses tendo um acréscimo de R$ 6,40 para cada 12 meses adicionais. Para aumentar o número de Planos (Padrão - 24 meses), o valor é de R$ 12,80 por Plano adicional. Para receber um Resumo Diário das análises e pendências, o que preciso pagar e receber hoje, quanto já gastei de supermercado até hoje, quanto já gastei nessa reforma, etc de seu Plano via Whatsapp terá um acréscimo de R$ 9,85 por Plano.
    </div>
    """, unsafe_allow_html=True)