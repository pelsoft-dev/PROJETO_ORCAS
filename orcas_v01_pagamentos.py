import streamlit as st
import mercadopago
import datetime

def criar_link_final(user_id, valor, descricao, email_usuario):
    """
    Gera a preferência de pagamento no Mercado Pago e retorna o link de checkout
    e o ID da preferência para futura verificação.
    """
    try:
        # Busca o token diretamente dos secrets para garantir atualização
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
            "external_reference": str(user_id), # Vincula o pagamento ao ID do usuário no Orcas
            "payment_methods": {
                "installments": 1 # Força pagamento à vista (Pix ou 1x Cartão)
            },
            "back_urls": {
                "success": "https://share.streamlit.io/",
                "failure": "https://share.streamlit.io/",
                "pending": "https://share.streamlit.io/"
            },
            "auto_return": "approved",
            "binary_mode": False # Permite estados pendentes (importante para Pix)
        }
        
        res = sdk.preference().create(preference_data)
        
        if res["status"] in [200, 201]:
            # Retornamos o link (init_point) e o ID (id) para o orcas_v01_gestao.py
            return res["response"].get("init_point"), res["response"].get("id")
        
        return None, None
        
    except Exception as e:
        # Log de erro silencioso para não quebrar a UI, mas retornando None
        return None, None

def verificar_pagamento(preference_id):
    """
    Consulta o Mercado Pago para verificar se existe um pagamento aprovado
    vinculado ao ID da preferência gerado anteriormente.
    """
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        sdk = mercadopago.SDK(token)
        
        # Filtramos a busca especificamente pelo preference_id
        # Isso evita confundir pagamentos antigos do mesmo usuário
        filtros = {
            "preference_id": str(preference_id)
        }
        
        resultado = sdk.payment().search(filtros)
        
        if resultado["status"] == 200:
            pagamentos = resultado["response"].get("results", [])
            
            # Percorre os resultados procurando por um status 'approved'
            for p in pagamentos:
                status = p.get("status")
                if status == "approved":
                    return True, p.get("payment_type_id") # Retorna True e o meio (pix, credit_card)
                    
        return False, None
        
    except Exception as e:
        # Se der erro na comunicação com a API
        return False, str(e)