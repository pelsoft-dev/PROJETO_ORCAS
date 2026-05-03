import streamlit as st
import mercadopago
import datetime

def criar_link_final(user_id, valor, descricao, email_usuario):
    try:
        sdk = mercadopago.SDK(st.secrets["MP_ACCESS_TOKEN"])
        preference_data = {
            "items": [{"title": descricao, "quantity": 1, "unit_price": float(round(valor, 2))}],
            "payer": {"email": email_usuario},
            "external_reference": str(user_id), # ID do usuário para identificar quem pagou
            "payment_methods": {"installments": 1},
            "back_urls": {
                "success": "https://share.streamlit.io/",
                "failure": "https://share.streamlit.io/",
                "pending": "https://share.streamlit.io/"
            },
            "auto_return": "approved"
        }
        res = sdk.preference().create(preference_data)
        if res["status"] in [200, 201]:
            # Retornamos o link E o ID da preferência
            return res["response"].get("init_point"), res["response"].get("id")
        return None, None
    except:
        return None, None

def verificar_pagamento(preference_id):
    try:
        sdk = mercadopago.SDK(st.secrets["MP_ACCESS_TOKEN"])
        # Consultamos os pagamentos associados a essa preferência
        resultado = sdk.payment().search({'order.id': preference_id})
        
        if resultado["status"] == 200:
            pagamentos = resultado["response"].get("results", [])
            for p in pagamentos:
                if p.get("status") == "approved":
                    return True, p.get("installments") # Pagamento confirmado
        return False, None
    except:
        return False, None