import streamlit as st
import mercadopago
import requests
from datetime import datetime, timedelta

def criar_link_final(user_id, valor, descricao, email_usuario, qtd_meses, url_origem):
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
            "external_reference": str(user_id),

            "back_urls": {
                "success": "https://orcas-planejamento-financeiro.streamlit.app/?status=success",
                "pending": "https://orcas-planejamento-financeiro.streamlit.app/?status=pending",
                "failure": "https://orcas-planejamento-financeiro.streamlit.app/?status=failure",
            },

            # "back_urls": {
            #     "success": f"{url_origem}?status=success",
            #     "pending": f"{url_origem}?status=pending",
            #     "failure": f"{url_origem}?status=failure",
            # },
            "notification_url": "https://hook.us2.make.com/youbq3bhry3422tjjahaqqmyrsr2o81e",
            "auto_return": "approved"
        }
        
        res = sdk.preference().create(preference_data)
        
        if res["status"] in [200, 201]:
            init_point = res["response"].get("init_point")
            preference_id = res["response"].get("id")
            return init_point, preference_id
        else:
            return None, None
            
    except Exception as e:
        st.error(f"Erro ao criar link de pagamento: {e}")
        return None, None

def consultar_pagamento_mp(user_id, pref_id=None, valor_esperado=None):
    """
    Consulta o Mercado Pago e retorna o valor pago apenas se:
    - for do usuário correto,
    - corresponder à preferência atual,
    - tiver sido criado nas últimas 24h,
    - e o valor for exatamente o esperado.
    """
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        headers = {"Authorization": f"Bearer {token}"}
        url = "https://api.mercadopago.com/v1/payments/search?status=approved&sort=date_created&criteria=desc&limit=10"
        res = requests.get(url, headers=headers).json()

        if res.get('results'):
            for pag in res['results']:
                # 1. Usuário correto
                if str(pag.get('external_reference')) != str(user_id):
                    continue
                # 2. Preferência correta
                if pref_id and pag.get('order', {}).get('id') != pref_id:
                    continue
                # 3. Pagamento recente
                data_pag = datetime.strptime(pag['date_created'][:19], "%Y-%m-%dT%H:%M:%S")
                if datetime.utcnow() - data_pag > timedelta(hours=24):
                    continue
                # 4. Valor correto
                valor_pago = pag.get('transaction_amount')
                if valor_esperado is not None and round(valor_pago, 2) != round(valor_esperado, 2):
                    continue
                return valor_pago
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