import streamlit as st
import mercadopago

def criar_link_final(user_id, valor, descricao, email_usuario, qtd_meses):
    """
    Cria a preferência de pagamento no Mercado Pago.
    O 'external_reference' leva o ID do usuário que o Make usará no PATCH.
    """
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        if not token:
            st.error("Token do Mercado Pago não encontrado nos Secrets.")
            return None, None
            
        sdk = mercadopago.SDK(token)
        
        preference_data = {
            "items": [{
                "id": str(qtd_meses), # Quantidade de meses para possível uso futuro
                "title": descricao,
                "quantity": 1,
                "unit_price": float(round(valor, 2))
            }],
            "payer": {"email": email_usuario},
            # CRUCIAL: O user_id enviado aqui deve ser o mesmo ID (int4) da tabela usuarios
            "external_reference": str(user_id), 
            "back_urls": {
                "success": "https://share.streamlit.io/", # Altere para a URL real do seu app se desejar
                "pending": "https://share.streamlit.io/",
                "failure": "https://share.streamlit.io/",
            },
            "notification_url": "https://hook.us2.make.com/youbq3bhry3422tjjahaqqmyrsr2o81e", # COLOQUE AQUI O LINK DO MAKE
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

# NOTA: A função verificar_pagamento abaixo tornou-se opcional, pois o Make
# atualiza o banco de forma assíncrona. O seu app deve agora consultar 
# o Supabase para saber se o status mudou.
def verificar_pagamento_no_banco(user_id, supabase_client):
    """
    Em vez de perguntar ao Mercado Pago, perguntamos ao nosso banco 
    se o Make já fez o trabalho dele.
    """
    try:
        res = supabase_client.table("usuarios").select("data_ult_assinat").eq("id", user_id).execute()
        if res.data:
            # Retorna a data gravada pelo Make para conferência no orcas_v01_gestao.py
            return res.data[0].get("data_ult_assinat")
        return None
    except Exception:
        return None