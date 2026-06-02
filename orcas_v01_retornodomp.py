import requests
from datetime import datetime
import zoneinfo
from dateutil.relativedelta import relativedelta
import streamlit as st

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno mapeando diretamente as colunas salvas no pagamentos_temp.
    Altera o status para 'concluido' em vez de deletar para evitar perdas em múltiplos reruns.
    """
    if status_retorno not in ["approved", "authorized", "pending"]:
        return None

    # 🌎 FIXAÇÃO DO FUSO HORÁRIO DO BRASIL (Evita o erro do dia seguinte)
    fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje_br = datetime.now(fuso_br).date()
    hoje_string = hoje_br.strftime('%Y-%m-%d')

    try:
        # 1. BUSCA O REGISTRO TEMPORÁRIO
        res_temp = supabase.table("pagamentos_temp")\
            .select("usuario_id, valor, pref_id, projeto_id, tipo_renovacao, data_ini, data_fim, zap_ativo, email_ativo")\
            .eq("pref_id", str(pref_id))\
            .eq("status", "aguardando")\
            .execute()
            
        # Se não encontrou com o pref_id, tenta buscar o último pendente do próprio usuário logado
        if not res_temp.data and "usuario_id" in st.session_state:
            res_temp = supabase.table("pagamentos_temp")\
                .select("usuario_id, valor, pref_id, projeto_id, tipo_renovacao, data_ini, data_fim, zap_ativo, email_ativo")\
                .eq("usuario_id", st.session_state.usuario_id)\
                .eq("status", "aguardando")\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()

        # Se a tabela já foi processada (status 'concluido'), faz o login preventivo com base no estado atual do banco
        if not res_temp.data:
            email_sessao = st.session_state.get("usuario_email")
            if email_sessao:
                res_user_final = supabase.table("usuarios").select("*").eq("email", email_sessao).execute()
                if res_user_final.data:
                    u = res_user_final.data[0]
                    return {
                        "id": u["id"], "nome": u["nome"], "email": u["email"],
                        "vencimento": u["vencimento"], "zap_ativo": u.get("zap_ativo", False),
                        "projeto_ativo": st.session_state.get("projeto_ativo")
                    }
            return None
            
        dados_pag_temp = res_temp.data[0]
        uid_usuario = dados_pag_temp["usuario_id"]
        valor_esperado = dados_pag_temp["valor"]
        pref_id_original = dados_pag_temp["pref_id"]
        nome_plano = dados_pag_temp.get("projeto_id")
        tipo_renov_escolhido = dados_pag_temp.get("tipo_renovacao")
        
        # 2. RECUPERAÇÃO DE INFORMAÇÕES CADASTRUTURAIS DO USUÁRIO
        res_user_atual = supabase.table("usuarios").select("vencimento, id, nome, email, zap_ativo").eq("id", uid_usuario).execute()
        user_db = res_user_atual.data[0]
        
        # 3. TRATAMENTO DO VENCIMENTO DA LICENÇA GERAL
        if tipo_renov_escolhido and "12" in str(tipo_renov_escolhido):
            meses_comprados = 12
        elif tipo_renov_escolhido and "6" in str(tipo_renov_escolhido):
            meses_comprados = 6
        elif tipo_renov_escolhido and "36" in str(tipo_renov_escolhido):
            meses_comprados = 36
        else:
            meses_comprados = 12 if valor_esperado > 150.00 else (6 if valor_esperado > 50.00 else 1)
            
        nova_data_vencimento_str = (hoje_br + relativedelta(months=meses_comprados)).strftime("%Y-%m-%d")

        # 5. ATUALIZA VALIDADE NA TABELA DE USUÁRIOS
        supabase.table("usuarios").update({
            "vencimento": nova_data_vencimento_str, 
            "data_ult_assinat": hoje_string, 
            "valor_pago": float(valor_esperado),
            "tipo_renovacao": tipo_renov_escolhido if tipo_renov_escolhido else "Personalizado"
        }).eq("id", uid_usuario).execute()
        
        # 6. ATUALIZA STATUS DA TEMPORÁRIA PARA CONCLUÍDO
        supabase.table("pagamentos_temp").update({"status": "concluido"}).eq("pref_id", pref_id_original).execute()
        
        # 7. 🚀 EXECUÇÃO CAMPO A CAMPO (Sem agrupamento/payload)
        # Primeiro, buscamos de forma fresca os campos isolados da pagamentos_temp
        res_dados_frescos = supabase.table("pagamentos_temp")\
            .select("projeto_id, data_ini, data_fim, zap_ativo, email_ativo")\
            .eq("pref_id", str(pref_id_original))\
            .execute()
            
        if res_dados_frescos.data:
            dados_frescos = res_dados_frescos.data[0]
            
            # Extração individual campo a campo
            v_projeto_id = dados_frescos.get("projeto_id") if dados_frescos.get("projeto_id") else "Plano Ativo"
            v_data_ini = dados_frescos.get("data_ini") if dados_frescos.get("data_ini") else hoje_string
            v_data_fim = dados_frescos.get("data_fim")
            v_zap_ativo = dados_frescos.get("zap_ativo")
            v_email_ativo = dados_frescos.get("email_ativo")
            
            # Verifica explicitamente se esse plano específico já tem um ID na config_projetos
            res_existente = supabase.table("config_projetos")\
                .select("id")\
                .eq("projeto_id", v_projeto_id)\
                .eq("usuario_id", uid_usuario)\
                .execute()

            # Se o registro já existir, nós fazemos um UPDATE direto mirando no ID numérico dele
            if res_existente.data:
                id_registro_oficial = res_existente.data[0]["id"]
                
                # Executa atualizações campo por campo no registro existente
                supabase.table("config_projetos").update({"data_ini": v_data_ini}).eq("id", id_registro_oficial).execute()
                supabase.table("config_projetos").update({"data_fim": v_data_fim}).eq("id", id_registro_oficial).execute()
                supabase.table("config_projetos").update({"zap_ativo": v_zap_ativo}).eq("id", id_registro_oficial).execute()
                supabase.table("config_projetos").update({"email_ativo": v_email_ativo}).eq("id", id_registro_oficial).execute()
            
            # Se o plano NÃO existir na tabela oficial, nós inserimos ele do zero com campos explícitos
            else:
                supabase.table("config_projetos").insert({
                    "projeto_id": v_projeto_id,
                    "usuario_id": uid_usuario,
                    "data_ini": v_data_ini,
                    "data_fim": v_data_fim,
                    "zap_ativo": v_zap_ativo,
                    "email_ativo": v_email_ativo
                }).execute()

            # Limpa lançamentos fora dos limites se houver data_fim
            if v_data_fim:
                supabase.table("lancamentos").delete().eq("projeto_id", v_projeto_id).eq("usuario_id", uid_usuario).gt("data", v_data_fim).execute()

        # 8. RETORNA O DICIONÁRIO COMPLETO DE SESSÃO COM OS DADOS ATUALIZADOS DO PLANO COMPRADO
        return {
            "id": user_db["id"], 
            "nome": user_db["nome"], 
            "email": user_db["email"],
            "vencimento": nova_data_vencimento_str, 
            "zap_ativo": dados_pag_temp.get("zap_ativo"), 
            "projeto_ativo": nome_plano if nome_plano else "Plano Ativo"
        }

    except Exception as e:
        print(f"--- [ERRO CRÍTICO RETORNO MP]: {e} ---")
        return None