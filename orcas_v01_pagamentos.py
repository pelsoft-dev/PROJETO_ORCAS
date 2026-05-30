import streamlit as st
import mercadopago
import requests
from datetime import datetime, timedelta, date
from calendar import monthrange

def calcular_proximo_vencimento(hoje, qtd_meses=1):
    """
    Regra Comercial D+Meses: Avança o mês mantendo o mesmo dia.
    Se a data original for o último dia do mês, o vencimento será o último dia do mês destino.
    """
    ano = hoje.year
    mes = hoje.month + qtd_meses
    
    while mes > 12:
        mes -= 12
        ano += 1
        
    dia_original = hoje.day
    _, ultimo_dia_atual = monthrange(hoje.year, hoje.month)
    _, ultimo_dia_destino = monthrange(ano, mes)
    
    if dia_original == ultimo_dia_atual:
        dia_destino = ultimo_dia_destino
    else:
        dia_destino = min(dia_original, ultimo_dia_destino)
        
    return date(ano, mes, dia_destino)

def criar_link_final(user_id, valor, descricao, email_usuario, qtd_meses, url_origem=None):
    """
    Cria a preferência de pagamento no Mercado Pago injetando os dados de bypass 
    e o cálculo preciso de vencimento comercial direto na URL de retorno.
    """
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        if not token:
            st.error("Token do Mercado Pago não encontrado nos Secrets.")
            return None, None
            
        sdk = mercadopago.SDK(token)
        plano_ativo = st.session_state.get('projeto_ativo', 'PLANO_PADRAO')
        
        # Calcula a data exata usando a regra comercial para enviar via URL
        hoje_dt = datetime.now().date()
        venc_calculado = calcular_proximo_vencimento(hoje_dt, int(qtd_meses))
        venc_str = venc_calculado.strftime('%Y-%m-%d')
        
        url_do_seu_app = "https://orcas-planejamento-financeiro.streamlit.app/"
        
        # Parâmetros injetados de forma limpa
        url_retorno_com_bypass = (
            f"{url_do_seu_app}?"
            f"bypass_uid={user_id}&"
            f"bypass_plano={plano_ativo}&"
            f"bypass_val={float(round(valor, 2))}&"
            f"bypass_venc={venc_str}"
        )
        
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
                "success": url_retorno_com_bypass,
                "pending": url_retorno_com_bypass,
                "failure": url_retorno_com_bypass,
            },
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
    try:
        token = st.secrets.get("MP_ACCESS_TOKEN")
        headers = {"Authorization": f"Bearer {token}"}
        url = "https://api.mercadopago.com/v1/payments/search?status=approved&sort=date_created&criteria=desc&limit=15"
        res = requests.get(url, headers=headers).json()

        if res.get('results'):
            for pag in res['results']:
                if str(pag.get('external_reference')) != str(user_id):
                    continue
                if pref_id and str(pag.get('preference_id')) != str(pref_id):
                    continue
                
                data_pag = datetime.strptime(pag['date_created'][:19], "%Y-%m-%dT%H:%M:%S")
                if datetime.utcnow() - data_pag > timedelta(hours=24):
                    continue
                    
                valor_pago = pag.get('transaction_amount')
                if valor_esperado is not None and round(valor_pago, 2) != round(valor_esperado, 2):
                    continue
                return valor_pago
        return None
    except Exception:
        return None

def verificar_pagamento_no_banco(user_id, supabase_client):
    try:
        res = supabase_client.table("usuarios").select("data_ult_assinat").eq("id", user_id).execute()
        if res.data:
            return res.data[0].get("data_ult_assinat")
        return None
    except Exception:
        return None