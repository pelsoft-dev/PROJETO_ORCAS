import streamlit as st
import mercadopago

def criar_link_final(user_id, valor, descricao, email_usuario="test_user_123@testuser.com"):
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        if not token:
            return None, None
            
        sdk = mercadopago.SDK(token)
        
        preference_data = {
            "items": [{"title": descricao, "quantity": 1, "unit_price": float(round(valor, 2))}],
            "payer": {"email": email_usuario},
            "external_reference": str(user_id),
            "payment_methods": {
                "excluded_payment_methods": [{"id": "consumer_credits"}],
                "installments": 1 
            },
            "back_urls": {
                "success": "https://share.streamlit.io/",
                "failure": "https://share.streamlit.io/",
                "pending": "https://share.streamlit.io/"
            },
            "auto_return": "approved",
            "binary_mode": False
        }
        
        res = sdk.preference().create(preference_data)
        if res["status"] in [200, 201]:
            # RETORNA LINK E ID DA PREFERÊNCIA
            return res["response"].get("init_point"), res["response"].get("id")
        return None, None
    except Exception:
        return None, None

def verificar_pagamento(preference_id):
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        sdk = mercadopago.SDK(token)
        # Busca pagamentos vinculados a este ID de preferência
        resultado = sdk.payment().search({"preference_id": str(preference_id)})
        
        if resultado["status"] == 200:
            results = resultado["response"].get("results", [])
            for p in results:
                if p.get("status") == "approved":
                    return True
        return False
    except Exception:
        return False