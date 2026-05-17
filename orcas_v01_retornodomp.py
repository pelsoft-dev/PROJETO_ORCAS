import streamlit as st
from datetime import date
import orcas_v01_pagamentos as pag

def tratar_retorno(supabase, ID_USUARIO_LOGADO):
    """
    Módulo de interceptação do retorno do Mercado Pago.
    Deve ser chamado antes da seção de login no orcasapp.py.
    """
    status_retorno = st.query_params.get("status", [None])[0]

    if not status_retorno:
        return  # nada a fazer

    if status_retorno == "success":
        st.info("⏳ Confirmando pagamento com o Mercado Pago...")

        confirmado_valor = pag.consultar_pagamento_mp(
            ID_USUARIO_LOGADO,
            st.session_state.get("pref_id_ativa"),
            st.session_state.get("valor_esperado")
        )

        if confirmado_valor:
            hoje = str(date.today())
            supabase.table("usuarios").update({
                "data_ult_assinat": hoje,
                "valor_pago": confirmado_valor
            }).eq("id", ID_USUARIO_LOGADO).execute()

            st.success(f"✅ Pagamento de R$ {confirmado_valor:.2f} Confirmado!")
            st.balloons()

            # Limpa flags de sessão
            if "url_ativa" in st.session_state:
                del st.session_state.url_ativa
            if "status_mp" in st.session_state:
                del st.session_state.status_mp

            st.stop()
        else:
            st.warning("O Mercado Pago ainda não confirmou o pagamento ou o valor não confere. Aguarde alguns segundos e recarregue.")
            st.stop()

    elif status_retorno == "pending":
        st.info("Pagamento ainda está pendente. Aguarde a confirmação.")
        st.stop()

    elif status_retorno == "failure":
        st.error("O pagamento não foi concluído. Tente novamente.")
        st.stop()