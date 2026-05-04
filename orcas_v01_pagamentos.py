import streamlit as st
import mercadopago

def criar_link_final(user_id, valor, descricao, email_usuario="cliente_geral@email.com"):
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        if not token:
            return None, None
            
        sdk = mercadopago.SDK(token)
        
        # Payload Mínimo: Sem restrições de métodos para forçar a volta do PIX
        preference_data = {
            "items": [{"title": descricao, "quantity": 1, "unit_price": float(round(valor, 2))}],
            "payer": {"email": email_usuario},
            "external_reference": str(user_id),
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
            # Retorna o link e o ID para o botão de verificação
            return res["response"].get("init_point"), res["response"].get("id")
        return None, None
    except Exception:
        return None, None

def verificar_pagamento(preference_id):
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        sdk = mercadopago.SDK(token)
        
        # Busca direta por preference_id
        resultado = sdk.payment().search({"preference_id": str(preference_id)})
        
        if resultado["status"] == 200:
            results = resultado["response"].get("results", [])
            for p in results:
                if p.get("status") == "approved":
                    return True
        return False
    except Exception:
        return False