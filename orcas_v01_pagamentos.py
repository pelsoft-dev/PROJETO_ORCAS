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
            "external_reference": str(user_id),
            "back_urls": {"success": "https://share.streamlit.io/", "failure": "https://share.streamlit.io/", "pending": "https://share.streamlit.io/"},
            "auto_return": "approved",
            "binary_mode": False
        }
        res = sdk.preference().create(preference_data)
        if res["status"] in [200, 201]:
            return res["response"].get("init_point"), res["response"].get("id")
        return None, None
    except Exception: return None, None

def verificar_pagamento(preference_id, user_id):
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        sdk = mercadopago.SDK(token)
        
        # 1. BUSCA POR EXTERNAL_REFERENCE (Seu User ID)
        # É a busca mais estável da API
        resultado = sdk.payment().search({
            "external_reference": str(user_id),
            "sort": "date_created",
            "order": "desc"
        })
        
        if resultado["status"] == 200:
            for p in resultado["response"].get("results", []):
                # Se o ID da preferência bater ou se for o pagamento mais recente aprovado deste usuário
                if str(p.get("preference_id")) == str(preference_id) and p.get("status") == "approved":
                    return True

        # 2. BUSCA GLOBAL RECENTE (Varredura de segurança)
        # Caso o MP tenha falhado em vincular o external_reference na hora
        resultado_geral = sdk.payment().search({
            "sort": "date_created",
            "order": "desc",
            "limit": 10
        })
        
        if resultado_geral["status"] == 200:
            for p in resultado_geral["response"].get("results", []):
                if str(p.get("preference_id")) == str(preference_id) and p.get("status") == "approved":
                    return True
                    
        return False
    except Exception:
        return False