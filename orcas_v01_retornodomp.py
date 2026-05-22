import requests
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import streamlit as st

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno de forma resiliente: localiza o pagamento pendente do usuário,
    atualiza sua assinatura calculando o vencimento comercial correto, recupera o plano 
    ativo salvo temporariamente, limpa o registro temporário e faz o login automático.
    """
    # Aceita approved, authorized e pending (comum em fluxos PIX reais no redirecionamento)
    if status_retorno not in ["approved", "authorized", "pending"]:
        return None

    try:
        # 1. LOCALIZAÇÃO DO REGISTRO TEMPORÁRIO
        # Como o pref_id vindo na URL pode ser o collection_id, tentamos buscar primeiro por ele.
        res_temp = supabase.table("pagamentos_temp")\
            .select("usuario_id, valor, pref_id, projeto_id")\
            .eq("pref_id", str(pref_id))\
            .execute()
            
        # CONTINGÊNCIA: Se não achou pelo ID (porque o MP mudou o parâmetro na URL),
        # buscamos o último pagamento que foi registrado no sistema para aquele fluxo.
        if not res_temp.data:
            res_temp = supabase.table("pagamentos_temp")\
                .select("usuario_id, valor, pref_id, projeto_id")\
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
        plano_salvo = dados_pag_temp.get("projeto_id") # Resgata o plano ativo salvo antes do pagamento
        
        # 2. BUSCA OS DADOS DO USUÁRIO PARA RENOVAÇÃO
        res_user_atual = supabase.table("usuarios")\
            .select("vencimento, id, nome, email, zap_ativo")\
            .eq("id", uid_usuario)\
            .execute()
            
        if not res_user_atual.data:
            return None
            
        user_db = res_user_atual.data[0]
        
        # Descobre a quantidade de meses contratada baseando-se no valor esperado armazenado
        # Buscamos o registro correspondente para garantir o multiplicador correto de meses
        meses_comprados = 1
        if "url_ativa" in st.session_state and st.session_state.get("pref_id_ativa") == pref_id_original:
            meses_comprados = st.session_state.get("meses_comprados", 1)
        else:
            # Contingência caso o session_state tenha limpado: inferência pelo valor estimado
            if valor_esperado > 150.00:  # Faixa de preço de planos anuais com desconto
                meses_comprados = 12
            elif valor_esperado > 50.00: # Faixa de preço de planos semestrais com desconto
                meses_comprados = 6

        # 3. CÁLCULO DO NOVO VENCIMENTO COMERCIAL (Último dia do mês alvo)
        # Regra solicitada:
        # Mensal (1 mês) -> Último dia do mês seguinte (+1 no multiplicador comercial = 2 meses à frente - 1 dia)
        # 6 Meses       -> Último dia do 7º mês à frente
        # 12 Meses      -> Último dia do 13º mês à frente
        hoje = date.today()
        
        # Deslocamento base para atingir o início do mês subsequente ao período contratado
        deslocamento_meses = meses_comprados + 1
        
        # Forçamos o cálculo comercial a partir do primeiro dia do mês atual para evitar distorções de dias vazios
        primeiro_dia_mes_atual = hoje.replace(day=1)
        
        # Avança até o primeiro dia do mês posterior ao período limite e subtrai 1 dia para pegar o último dia exato
        nova_data_vencimento = (primeiro_dia_mes_atual + relativedelta(months=deslocamento_meses)) - timedelta(days=1)
        
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
        
        # 6. RETORNA O DICIONÁRIO COMPLETO PARA O BYPASS DE LOGIN (Incluindo o plano reativado)
        return {
            "id": user_db["id"],
            "nome": user_db["nome"],
            "email": user_db["email"],
            "vencimento": nova_data_vencimento.strftime("%Y-%m-%d"),
            "zap_ativo": user_db["zap_ativo"],
            "projeto_ativo": plano_salvo # Injetado para o app restaurar a sessão do plano automaticamente
        }

    except Exception as e:
        print(f"Erro crítico no processamento do retorno: {e}")
        return None