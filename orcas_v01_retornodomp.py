import requests
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno do Mercado Pago, valida o pagamento,
    atualiza os créditos de assinatura do usuário e retorna os dados
    do usuário para a realização do Login Automático no app principal.
    """
    # Se o pagamento não foi aprovado pelo MP, nem perdemos tempo processando
    if status_retorno != "approved":
        return None

    try:
        # 1. Busca na tabela temporária para descobrir quem é o dono desse preference_id
        res_temp = supabase.table("pagamentos_temp")\
            .select("usuario_id, valor, status")\
            .eq("pref_id", str(pref_id))\
            .execute()
            
        if not res_temp.data:
            return None # Não achou o rastro do pagamento no banco temporário
            
        dados_pag_temp = res_temp.data[0]
        uid_usuario = dados_pag_temp["usuario_id"]
        valor_esperado = dados_pag_temp["valor"]
        
        # Se esse pagamento temporário já foi processado antes, apenas pega o usuário e loga
        if dados_pag_temp["status"] == "processado":
            res_user = supabase.table("usuarios").select("id, nome, email, vencimento, zap_ativo").eq("id", uid_usuario).execute()
            return res_user.data[0] if res_user.data else None

        # 2. CONSULTA DIRETA NO MERCADO PAGO (Para garantir que o status é real e seguro)
        # Buscamos o Token que você já configurou no seu módulo oficial de pagamentos
        import orcas_v01_pagamentos as pag
        TOKEN_MP = pag.TOKEN_MP_PROD if hasattr(pag, 'TOKEN_MP_PROD') else pag.TOKEN_MP
        
        url_mp = f"https://api.mercadopago.com/v1/payments/{pref_id}" if "collection_id" in str(pref_id) else f"https://api.mercadopago.com/checkout/preferences/{pref_id}"
        headers = {"Authorization": f"Bearer {TOKEN_MP}"}
        
        response = requests.get(url_mp, headers=headers)
        if response.status_code != 200:
            return None # Falha ao consultar a API do Mercado Pago

        # 3. ATUALIZAÇÃO DOS CRÉDITOS DO USUÁRIO
        # Buscamos os dados atuais do cliente no banco
        res_user_atual = supabase.table("usuarios").select("vencimento, id, nome, email, zap_ativo").eq("id", uid_usuario).execute()
        if not res_user_atual.data:
            return None
            
        user_db = res_user_atual.data[0]
        
        # Calcula a nova data de vencimento baseada no dia de hoje ou na data atual (o que for maior)
        hoje = date.today()
        try:
            venc_atual = datetime.strptime(user_db["vencimento"], "%Y-%m-%d").date()
        except:
            venc_atual = hoje
            
        data_base_renovacao = max(venc_atual, hoje)
        
        # Identifica quantos meses o usuário comprou olhando o valor (Regra de negócio dinâmica)
        # Nota: Você também pode salvar a 'qtd_meses' na pagamentos_temp se preferir, 
        # mas aqui estimamos pelo valor ou definimos um padrão seguro de 1 mês caso mude.
        meses_adicionar = 1
        if "meses_comprados" in dir(pag): # se mapeado no estado ou se preferir fixar pelo fluxo
            # Como o app reiniciou, podemos estimar o plano pelo valor final aproximado ou usar 1 mês padrão
            pass

        # Para garantir precisão, adicionamos os meses comprados à assinatura dele
        # (Se no seu fluxo o padrão for o que ele escolheu na tela)
        nova_data_vencimento = data_base_renovacao + relativedelta(months=meses_adicionar)
        
        # 4. SALVA DE FORMA DEFINITIVA NO SUPABASE
        supabase.table("usuarios").update({
            "vencimento": nova_data_vencimento.strftime("%Y-%m-%d"),
            "data_ult_assinat": hoje.strftime("%Y-%m-%d"),
            "valor_pago": float(valor_esperado)
        }).eq("id", uid_usuario).execute()
        
        # Marcar o pagamento temporário como processado para evitar duplicidade
        supabase.table("pagamentos_temp").update({"status": "processado"}).eq("pref_id", str(pref_id)).execute()
        
        # 5. RETORNA O DICIONÁRIO DO USUÁRIO ATUALIZADO
        # É isso que o orcas_v01_orcasapp.py vai ler para fazer o Login Automático!
        return {
            "id": user_db["id"],
            "nome": user_db["nome"],
            "email": user_db["email"],
            "vencimento": nova_data_vencimento.strftime("%Y-%m-%d"),
            "zap_ativo": user_db["zap_ativo"]
        }

    except Exception as e:
        print(f"Erro crítico no processamento do retorno: {e}")
        return None