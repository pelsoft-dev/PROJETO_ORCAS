import streamlit as st
from datetime import date
import orcas_v01_pagamentos as pag

def tratar_retorno(supabase, _):
    """
    Módulo de interceptação do retorno do Mercado Pago.
    Deve ser chamado logo no início do orcasapp.py,
    antes da seção de login.
    """

    # Captura parâmetros da URL
    status_retorno = st.query_params.get("status", [None])[0]
    pref_id = st.query_params.get("preference_id", [None])[0] or st.query_params.get("collection_id", [None])[0]

    if not status_retorno:
        return

    # Recupera o usuário e o valor esperado
    res = supabase.table("pagamentos_temp").select("usuario_id, valor").eq("pref_id", pref_id).execute()
    if not res.data:
        st.error("Não foi possível identificar o usuário do pagamento.")
        st.stop()

    usuario_id = res.data[0]["usuario_id"]
    valor_esperado = res.data[0]["valor"]

    # --- TRATAMENTO POR STATUS ---
    if status_retorno == "success":
        st.info("⏳ Confirmando pagamento com o Mercado Pago...")

        confirmado_valor = pag.consultar_pagamento_mp(usuario_id, pref_id, valor_esperado)

        if confirmado_valor:
            hoje = str(date.today())
            supabase.table("usuarios").update({
                "data_ult_assinat": hoje,
                "valor_pago": confirmado_valor
            }).eq("id", usuario_id).execute()

            supabase.table("pagamentos_temp").update({"status": "confirmado"}).eq("pref_id", pref_id).execute()

            st.success(f"✅ Pagamento de R$ {confirmado_valor:.2f} confirmado!")
            st.balloons()
            st.stop()
        else:
            st.warning("O Mercado Pago ainda não confirmou o pagamento. Aguarde alguns segundos e recarregue.")
            st.stop()

    elif status_retorno == "pending":
        supabase.table("pagamentos_temp").update({"status": "pendente"}).eq("pref_id", pref_id).execute()
        st.info("Pagamento ainda está pendente. Aguarde a confirmação.")
        st.stop()

    elif status_retorno == "failure":
        supabase.table("pagamentos_temp").update({"status": "falhou"}).eq("pref_id", pref_id).execute()
        st.error("O pagamento não foi concluído. Tente novamente.")
        st.stop()