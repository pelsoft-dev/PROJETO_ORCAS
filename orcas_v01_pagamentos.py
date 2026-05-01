import streamlit as st
import mercadopago

# def criar_link_final(user_id, valor, descricao):
#    """
#    Função técnica que gera a preferência no Mercado Pago.
#    Esta função é chamada pelo módulo de Gestão.
#    """
#    try:
#        # Configura o SDK com seu Token Privado
#        sdk = mercadopago.SDK(st.secrets["MP_ACCESS_TOKEN"])
#        
#        # Monta os dados da reserva/pagamento
#        preference_data = {
#            "items": [
#                {
#                    "title": descricao,
#                    "quantity": 1,
#                    "unit_price": float(valor),
#                }
#            ],
#            "external_reference": str(user_id),
#            "payment_methods": {
#                "excluded_payment_methods": [
#                    {"id": "consumer_credits"} # Remove a opção de crédito do Mercado Pago
#                ],
#                "installments": 1 # Força a exibição do valor à vista
#            },
#            "back_urls": {
#                "success": "https://seu-app.streamlit.app/", 
#                "failure": "https://seu-app.streamlit.app/",
#                "pending": "https://seu-app.streamlit.app/"
#            },
#            "auto_return": "approved",
#        }
#        
#        # Cria a preferência no servidor do Mercado Pago
#        res = sdk.preference().create(preference_data)
#        
#        # Retorna o link de pagamento (init_point)
#        return res["response"]["init_point"]
#        
#    except Exception as e:
#        st.error(f"Erro técnico no Mercado Pago: {e}")
#        return None

def criar_link_final(user_id, valor, descricao):
    try:
        sdk = mercadopago.SDK(st.secrets["MP_ACCESS_TOKEN"])
        preference_data = {
            "items": [{"title": descricao, "quantity": 1, "unit_price": float(valor)}],
            "external_reference": str(user_id),
            "payment_methods": {
                "excluded_payment_methods": [{"id": "consumer_credits"}],
                "installments": 1 
            },
            "auto_return": "approved",
        }
        res = sdk.preference().create(preference_data)
        return res["response"].get("init_point")
    except Exception as e:
        st.error(f"Erro técnico MP: {e}")
        return None

# Você pode manter a função exibir_pagamentos vazia ou removê-la, 
# já que agora a Gestão fará o trabalho visual.
def exibir_pagamentos(supabase, ID_USUARIO_LOGADO):
    st.write("Esta tela foi integrada à Gestão.")