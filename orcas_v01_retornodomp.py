import requests
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import streamlit as st

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno de forma resiliente: localiza o pagamento pendente do usuário,
    atualiza sua assinatura, limpa o registro temporário e faz o login automático.
    """
    # Se o status do Mercado Pago não for de sucesso, cancela o bypass
    if status_retorno != "approved" and status_retorno != "authorized":
        return None

    try:
        # 1. LOCALIZAÇÃO DO REGISTRO TEMPORÁRIO
        # Como o pref_id vindo na URL pode ser o collection_id, tentamos buscar primeiro por ele.
        res_temp = supabase.table("pagamentos_temp")\
            .select("usuario_id, valor, pref_id")\
            .eq("pref_id", str(pref_id))\
            .execute()
            
        # CONTINGÊNCIA: Se não achou pelo ID (porque o MP mudou o parâmetro na URL),
        # buscamos o último pagamento que foi registrado como 'pendente' no sistema.
        if not res_temp.data:
            res_temp = supabase.table("pagamentos_temp")\
                .select("usuario_id, valor, pref_id")\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()

        # Se mesmo com a contingência não houver registros iniciados, bloqueia por segurança
        if not res_temp.data:
            print("Nenhum rastro de pagamento pendente foi encontrado no banco.")
            return None
            
        dados_pag_temp = res_temp.data[0]
        uid_usuario = dados_pag_temp["usuario_id"]
        valor_esperado = dados_pag_temp["valor"]
        pref_id_original = dados_pag_temp["pref_id"]
        
        # 2. BUSCA OS DADOS DO USUÁRIO PARA RENOVAÇÃO
        res_user_atual = supabase.table("usuarios")\
            .select("vencimento, id, nome, email, zap_ativo")\
            .eq("id", uid_usuario)\
            .execute()
            
        if not res_user_atual.data:
            return None
            
        user_db = res_user_atual.data[0]
        
        # 3. CÁLCULO DO NOVO VENCIMENTO (+1 Mês)
        hoje = date.today()
        try:
            venc_atual = datetime.strptime(user_db["vencimento"], "%Y-%m-%d").date()
        except:
            venc_atual = hoje
            
        # Se já venceu, conta a partir de hoje. Se ainda estava válido, acumula na frente.
        data_base_renovacao = max(venc_atual, hoje)
        nova_data_vencimento = data_base_renovacao + relativedelta(months=1)
        
        # 4. ATUALIZA OS CRÉDITOS NA TABELA USUÁRIOS
        supabase.table("usuarios").update({
            "vencimento": nova_data_vencimento.strftime("%Y-%m-%d"),
            "data_ult_assinat": hoje.strftime("%Y-%m-%d"),
            "valor_pago": float(valor_esperado)
        }).eq("id", uid_usuario).execute()
        
        # 5. LIMPEZA: Deleta o registro para não deixar lixo na tabela temporária
        supabase.table("pagamentos_temp")\
            .delete()\
            .eq("pref_id", pref_id_original)\
            .execute()
        
        # 6. RETORNA O DICIONÁRIO COMPLETO PARA O BYPASS DE LOGIN
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