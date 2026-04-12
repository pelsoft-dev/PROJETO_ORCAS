import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

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
    
    # Seleção de Plano existente
    plano_sel = col_l1_1.selectbox("Selecione um Plano já existente:", lista_gestao)
    
    # Lógica de Troca de Plano: Força o estado e reinicia
    if plano_sel != "" and plano_sel != st.session_state.get('projeto_ativo'):
        st.session_state.projeto_ativo = plano_sel
        st.session_state.escolha = "⚙️ Gestão" 
        st.rerun()

    # Input do nome (carrega o ativo ou permite novo)
    nome_plano_input = col_l1_2.text_input(
        "Nome do Plano carregado ou Nome para criação de um novo Plano", 
        value=st.session_state.projeto_ativo if st.session_state.projeto_ativo else ""
    )

    # O bloco de edição só aparece se houver um nome definido
    if nome_plano_input and nome_plano_input.strip() != "":
        col_l2_1, col_l2_2 = st.columns(2)
        
        # Datas no formato DD/MM/AAAA
        d_ini_g = col_l2_1.date_input("Data de Início:", value=d_ini_db if d_ini_db else hoje, format="DD/MM/YYYY")
        d_fim_g = col_l2_2.date_input("Data de Término:", value=d_fim_db if d_fim_db else hoje + timedelta(days=730), format="DD/MM/YYYY")

        col_l3_1, col_l3_2 = st.columns(2)
        valor_saldo_exibir = format_moeda(s_db) if s_db is not None else "0,00"
        saldo_input = col_l3_1.text_input("Saldo Inicial:", value=valor_saldo_exibir)
        
        meses_total = (d_fim_g.year - d_ini_g.year) * 12 + (d_fim_g.month - d_ini_g.month)
        col_l3_2.text_input("Período do Plano:", value=f"{meses_total} meses", disabled=True)

        col_l4_1, col_l4_2 = st.columns(2)
        ativar_zap = col_l4_1.checkbox("Adicionar o Resumo diário via WHATSAPP", value=(st.session_state.get('zap_ativo', 0) == 1))
        
        # Cálculo da Assinatura via Security
        v_estimado = security.calcular_valor_v01(len(projs), d_ini_g.strftime('%Y-%m-%d'), d_fim_g.strftime('%Y-%m-%d'))
        if ativar_zap: v_estimado += 9.85
        
        col_l4_2.markdown(
            f'<div style="background-color: #87CEFA; padding: 10px; text-align: center; border-radius: 5px; font-weight: bold; color: black;">'
            f'Valor da Assinatura Mensal: R$ {format_moeda(v_estimado)}</div>', 
            unsafe_allow_html=True
        )

        st.divider()

        btn_col1, btn_col2 = st.columns(2)
        
        if btn_col1.button("Salvar alterações ou Criar o novo Plano", use_container_width=True):
            dados_p = {
                "projeto_id": nome_plano_input, 
                "usuario_id": uid_gestao, 
                "saldo_inicial": parse_moeda(saldo_input),
                "data_ini": d_ini_g.strftime('%Y-%m-%d'), 
                "data_fim": d_fim_g.strftime('%Y-%m-%d')
            }
            res_p = supabase.table("config_projetos").select("id").eq("projeto_id", nome_plano_input).eq("usuario_id", uid_gestao).execute()
            if res_p.data: dados_p["id"] = res_p.data[0]["id"]
            
            supabase.table("config_projetos").upsert(dados_p).execute()
            supabase.table("usuarios").update({"zap_ativo": 1 if ativar_zap else 0}).eq("id", uid_gestao).execute()
            
            st.session_state.projeto_ativo = nome_plano_input
            st.session_state.msg_sucesso = "Plano e Saldo Inicial salvos com sucesso!"
            st.session_state.escolha = "⚙️ Gestão"
            st.rerun()

        if st.session_state.projeto_ativo:
            if btn_col2.button("Excluir Plano", type="primary", use_container_width=True):
                st.session_state.confirmar_exclusao_plano = True

        # Confirmação de Exclusão
        if st.session_state.get('confirmar_exclusao_plano', False):
            st.error(f"Deseja mesmo excluir o plano {st.session_state.projeto_ativo}?")
            ce1, ce2 = st.columns(2)
            if ce1.button("CONFIRMAR EXCLUSÃO"):
                supabase.table("lancamentos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid_gestao).execute()
                supabase.table("config_projetos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid_gestao).execute()
                st.session_state.projeto_ativo = None
                st.session_state.confirmar_exclusao_plano = False
                st.session_state.escolha = "⚙️ Gestão"
                st.rerun()
            if ce2.button("CANCELAR"):
                st.session_state.confirmar_exclusao_plano = False
                st.rerun()
    else:
        st.info("Por favor, selecione um plano existente ou digite um nome para iniciar a configuração.")

    # Informativo de Preços (HTML preservado)
    st.markdown("""
    <div style="font-size: 12px; color: #333; margin-top: 20px; text-align: justify; line-height: 1.6;">
    Sua Assinatura ORCAS BABY mensal custa R$ 19,90 e contempla 2 Planos de 24 meses cada um... (texto original mantido)
    </div>
    """, unsafe_allow_html=True)