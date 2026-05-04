import streamlit as st
import mercadopago

def criar_link_final(user_id, valor, descricao, email_usuario="cliente@email.com"):
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        if not token: return None, None
        sdk = mercadopago.SDK(token)
        
        preference_data = {
            "items": [{"title": descricao, "quantity": 1, "unit_price": float(round(valor, 2))}],
            "payer": {"email": email_usuario},
            "external_reference": str(user_id), # USAMOS ISSO PARA BUSCAR DEPOIS
            "back_urls": {"success": "https://share.streamlit.io/", "failure": "https://share.streamlit.io/", "pending": "https://share.streamlit.io/"},
            "auto_return": "approved",
            "binary_mode": False
        }
        res = sdk.preference().create(preference_data)
        if res["status"] in [200, 201]:
            return res["response"].get("init_point"), res["response"].get("id")
        return None, None
    except Exception: return None, None

def verificar_pagamento(preference_id, user_id): # ADICIONAMOS USER_ID AQUI
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        sdk = mercadopago.SDK(token)
        
        # BUSCA PELO USER_ID (EXTERNAL_REFERENCE) - MUITO MAIS RÁPIDO
        filtros = {
            "external_reference": str(user_id),
            "sort": "date_created",
            "order": "desc"
        }
        
        resultado = sdk.payment().search(filtros)
        
        if resultado["status"] == 200:
            pagamentos = resultado["response"].get("results", [])
            for p in pagamentos:
                # Se o status for aprovado E o preference_id bater (para não pegar pagamento antigo)
                if p.get("status") == "approved" and str(p.get("preference_id")) == str(preference_id):
                    return True
        return False
    except Exception: return False