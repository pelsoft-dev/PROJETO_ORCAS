import streamlit as st
import mercadopago

def criar_link_final(user_id, valor, descricao, email_usuario="test_user_123@testuser.com"):
    """
    Gera a preferência de pagamento e retorna (link, preference_id).
    """
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        if not token:
            return None, None
            
        sdk = mercadopago.SDK(token)
        
        preference_data = {
            "items": [
                {
                    "title": descricao,
                    "quantity": 1,
                    "unit_price": float(round(valor, 2))
                }
            ],
            "payer": {
                "email": email_usuario
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
            "auto_return": "approved",
            "binary_mode": False
        }
        
        res = sdk.preference().create(preference_data)
        if res["status"] in [200, 201]:
            return res["response"].get("init_point"), res["response"].get("id")
        return None, None
    except Exception:
        return None, None

def verificar_pagamento(preference_id):
    """
    Verifica se o pagamento foi aprovado usando busca direta e varredura de segurança.
    """
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        if not token:
            return False
            
        sdk = mercadopago.SDK(token)
        
        # 1. TENTATIVA: Busca filtrada pelo preference_id
        # (Às vezes o MP demora alguns minutos para indexar essa busca)
        resultado = sdk.payment().search({"preference_id": str(preference_id)})
        
        if resultado["status"] == 200:
            pagamentos = resultado["response"].get("results", [])
            for p in pagamentos:
                if p.get("status") == "approved":
                    return True
        
        # 2. TENTATIVA (VARREDURA): Busca os últimos 10 pagamentos da conta
        # Útil caso a indexação do filtro acima esteja atrasada.
        resultado_geral = sdk.payment().search({
            "sort": "date_created", 
            "order": "desc", 
            "limit": 10
        })
        
        if resultado_geral["status"] == 200:
            pagamentos_gerais = resultado_geral["response"].get("results", [])
            for p in pagamentos_gerais:
                # Verifica se o ID da preferência bate com o que temos na sessão
                # E se o status é aprovado
                if str(p.get("preference_id")) == str(preference_id) and p.get("status") == "approved":
                    return True
                    
        return False
    except Exception:
        return False