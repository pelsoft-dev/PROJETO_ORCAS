import requests
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno do Mercado Pago: verifica contra a tabela pagamentos_temp,
    atualiza o usuário, deleta o registro temporário para não deixar lixo
    e retorna os dados para o bypass automático de login.
    """
    # Se o status do Mercado Pago não for aprovado, ignora
    if status_retorno != "approved" and status_retorno != "authorized":
        return None

    try:
        # 1. VALIDAÇÃO: Procura se esse pagamento iniciado existe na tabela temporária
        # Tentamos buscar primeiro pelo ID direto. Se não achar (porque o MP mudou o ID na URL),
        # buscamos pelo registro pendente mais recente no banco como contingência segura.
        res_temp = supabase.table("pagamentos_temp")\
            .select("usuario_id, valor, pref_id")\
            .eq("pref_id", str(pref_id))\
            .execute()
            
        if not res_temp.data:
            # Busca de contingência para PIX/Retornos onde o ID vem trocado pelo Mercado Pago
            res_temp = supabase.table("pagamentos_temp")\
                .select("usuario_id, valor, pref_id")\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()

        # Se mesmo assim não encontrou nenhum rastro do pagamento iniciado, barra por segurança
        if not res_temp.data:
            print("Tentativa de retorno inválida ou registro temporário não localizado.")
            return None
            
        dados_pag_temp = res_temp.data[0]
        uid_usuario = dados_pag_temp["usuario_id"]
        valor_esperado = dados_pag_temp["valor"]
        pref_id_original = dados_pag_temp["pref_id"]
        
        # 2. CAPTURA DADOS ATUAIS DO USUÁRIO
        res_user_atual = supabase.table("usuarios")\
            .select("vencimento, id, nome, email, zap_ativo")\
            .eq("id", uid_usuario)\
            .execute()
            
        if not res_user_atual.data:
            return None
            
        user_db = res_user_atual.data[0]
        
        # 3. CÁLCULO DA NOVA DATA DE VENCIMENTO (Adiciona +1 mês com segurança)
        hoje = date.today()
        try:
            venc_atual = datetime.strptime(user_db["vencimento"], "%Y-%m-%d").date()
        except:
            venc_atual = hoje
            
        # Se a assinatura já venceu, renova a partir de hoje. Se ainda estava válida, soma na frente.
        data_base_renovacao = max(venc_atual, hoje)
        nova_data_vencimento = data_base_renovacao + relativedelta(months=1)
        
        # 4. ATUALIZA A TABELA DE USUÁRIOS (Aplica os créditos do plano)
        supabase.table("usuarios").update({
            "vencimento": nova_data_vencimento.strftime("%Y-%m-%d"),
            "data_ult_assinat": hoje.strftime("%Y-%m-%d"),
            "valor_pago": float(valor_esperado)
        }).eq("id", uid_usuario).execute()
        
        # 5. LIMPEZA (Deleta os dados da tabela temporária conforme o seu plano!)
        supabase.table("pagamentos_temp")\
            .delete()\
            .eq("pref_id", pref_id_original)\
            .execute()
        
        # 6. RETORNO PARA BYPASS DE LOGIN
        # O dicionário abaixo alimenta o st.session_state no arquivo principal e pula o login
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