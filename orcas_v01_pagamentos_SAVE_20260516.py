import streamlit as st
import mercadopago

def criar_link_final(user_id, valor, descricao, email_usuario, qtd_meses):
    """
    Cria a preferência de pagamento no Mercado Pago.
    O 'external_reference' leva o ID do usuário para vincular a transação.
    """
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        if not token:
            st.error("Token do Mercado Pago não encontrado nos Secrets.")
            return None, None
            
        sdk = mercadopago.SDK(token)
        
        preference_data = {
            "items": [{
                "id": str(qtd_meses),
                "title": descricao,
                "quantity": 1,
                "unit_price": float(round(valor, 2))
            }],
            "payer": {"email": email_usuario},
            # Vincula o ID do usuário (ex: 1) à transação
            "external_reference": str(user_id), 
            "back_urls": {
                "success": "https://share.streamlit.io/",
                "pending": "https://share.streamlit.io/",
                "failure": "https://share.streamlit.io/",
            },
            "notification_url": "https://hook.us2.make.com/youbq3bhry3422tjjahaqqmyrsr2o81e",
            "auto_return": "approved"
        }
        
        res = sdk.preference().create(preference_data)
        
        if res["status"] == 201 or res["status"] == 200:
            init_point = res["response"].get("init_point")
            preference_id = res["response"].get("id")
            return init_point, preference_id
        else:
            return None, None
            
    except Exception as e:
        st.error(f"Erro ao criar link de pagamento: {e}")
        return None, None

def consultar_pagamento_mp(user_id):
    """
    Consulta o Mercado Pago buscando pelo external_reference (ID do usuário).
    Busca ampla nos últimos pagamentos aprovados para evitar erros de indexação.
    """
    import requests
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Buscamos os últimos 10 pagamentos aprovados na conta
        # Filtrar por external_reference diretamente na URL às vezes falha no Pix, 
        # por isso buscamos os recentes e conferimos no código.
        url = "https://api.mercadopago.com/v1/payments/search?status=approved&sort=date_created&criteria=desc&limit=10"
        res = requests.get(url, headers=headers).json()
        
        if res.get('results'):
            for pag in res['results']:
                # Verifica se o ID do usuário (external_reference) bate com o que buscamos
                if str(pag.get('external_reference')) == str(user_id):
                    return pag.get('transaction_amount')
        return None
    except Exception:
        return None

def verificar_pagamento_no_banco(user_id, supabase_client):
    """
    Verifica no Supabase se a data da última assinatura foi atualizada hoje.
    """
    try:
        res = supabase_client.table("usuarios").select("data_ult_assinat").eq("id", user_id).execute()
        if res.data:
            return res.data[0].get("data_ult_assinat")
        return None
    except Exception:
        return None