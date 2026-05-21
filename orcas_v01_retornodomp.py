import streamlit as st
from datetime import date
import orcas_v01_pagamentos as pag
import time

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Módulo de interceptação do retorno do Mercado Pago.
    Captura o retorno e processa visualmente para o usuário.
    """
    st.markdown("### ⏳ Processando Retorno do Mercado Pago...")
    
    # Recupera o usuário e o valor esperado
    try:
        res = supabase.table("pagamentos_temp").select("usuario_id, valor").eq("pref_id", str(pref_id)).execute()
        if not res.data:
            st.error("Não foi possível identificar o lote/usuário deste pagamento.")
            st.info("Caso tenha pago, não se preocupe! Seu acesso será validado manualmente em instantes.")
            return
    except Exception as e:
        st.error(f"Erro ao consultar banco temporário: {e}")
        return

    usuario_id = res.data[0]["usuario_id"]
    valor_esperado = res.data[0]["valor"]

    if status_retorno == "success":
        placeholder = st.empty()
        tempo_limite = 30  # Tempo curto de loop na volta da aba
        inicio = time.time()
        confirmado = False
        confirmado_valor = 0

        with placeholder.container():
            st.info("🔄 Validando transação em tempo real... Por favor, aguarde.")
            with st.spinner("Conectando à API de liquidação..."):
                progresso = st.progress(0)
                
                while time.time() - inicio < tempo_limite:
                    # Consulta robusta cruzando usuário, preferência e valor esperado
                    confirmado_valor = pag.consultar_pagamento_mp(usuario_id, pref_id, valor_esperado)
                    
                    if confirmado_valor:
                        confirmado = True
                        hoje = str(date.today())
                        # Atualiza a tabela definitiva de usuários
                        supabase.table("usuarios").update({
                            "data_ult_assinat": hoje,
                            "valor_pago": confirmado_valor
                        }).eq("id", usuario_id).execute()

                        # Limpa o temporário
                        supabase.table("pagamentos_temp").update({"status": "confirmado"}).eq("pref_id", pref_id).execute()
                        break
                    
                    decorrido = time.time() - inicio
                    progresso.progress(min(decorrido / tempo_limite, 1.0))
                    time.sleep(3)

        placeholder.empty()

        if confirmado:
            st.balloons()
            st.success(f"🎉 Excelente! Pagamento de R$ {confirmado_valor:.2f} confirmado com sucesso!")
            st.info("Clique no botão abaixo para entrar na sua conta atualizada.")
            if st.button("🚀 Acessar o Painel Principal", use_container_width=True):
                st.query_params.clear()
                st.rerun()
        else:
            st.warning("⚠️ O Mercado Pago registrou o sucesso, mas a API de consulta está instável.")
            st.info("Seu pagamento foi recebido! Nossa equipe já foi notificada para liberar seu painel em minutos.")
            if st.button("Voltar ao Início"):
                st.query_params.clear()
                st.rerun()

    elif status_retorno == "pending":
        supabase.table("pagamentos_temp").update({"status": "pendente"}).eq("pref_id", pref_id).execute()
        st.info("⏳ Seu Pix/Boleto consta como pendente. Assim que compensar, sua conta será liberada automaticamente.")
        if st.button("Voltar ao Menu"):
            st.query_params.clear()
            st.rerun()

    elif status_retorno == "failure":
        supabase.table("pagamentos_temp").update({"status": "falhou"}).eq("pref_id", pref_id).execute()
        st.error("❌ O Mercado Pago informou que a transação foi recusada ou cancelada.")
        if st.button("Tentar Novamente"):
            st.query_params.clear()
            st.rerun()