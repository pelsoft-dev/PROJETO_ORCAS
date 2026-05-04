import streamlit as st
import mercadopago

def criar_link_final(user_id, valor, descricao, email_usuario="test_user_123@testuser.com"):
    try:
        # Puxa o token dos secrets
        token = st.secrets.get("MP_ACCESS_TOKEN")
        if not token:
            return None
            
        sdk = mercadopago.SDK(token)
        
        # Payload ajustado para evitar pedido de login e habilitar PIX
        preference_data = {
            "items": [
                {
                    "title": descricao,
                    "quantity": 1,
                    "unit_price": float(round(valor, 2))
                }
            ],
            "payer": {
                "email": email_usuario  # ENVIAR O E-MAIL EVITA QUE O MP PEÇA LOGIN OBRIGATÓRIO
            },
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
            "auto_return": "approved"
        }
        
        res = sdk.preference().create(preference_data)
        if res["status"] in [200, 201]:
            return res["response"].get("init_point")
        else:
            return None
    except Exception:
        return None