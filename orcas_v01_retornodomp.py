import requests
from datetime import datetime
import zoneinfo
from dateutil.relativedelta import relativedelta
import streamlit as st

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno mapeando diretamente as colunas salvas no pagamentos_temp.
    Altera o status para 'concluido' e, ao final, limpa o histórico temporário do usuário.
    """
    if status_retorno not in ["approved", "authorized", "pending"]:
        return None

    # 🌎 FIXAÇÃO DO FUSO HORÁRIO DO BRASIL (Evita o erro do dia seguinte)
    fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje_br = datetime.now(fuso_br).date()
    hoje_string = hoje_br.strftime('%Y-%m-%d')

    try:
        # 1. BUSCA O REGISTRO TEMPORÁRIO QUE AINDA ESTÁ AGUARDANDO
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
                .limit(1)\
                .execute()

        # Se a tabela já foi processada (status 'concluido'), faz o login com base no estado atual do banco
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
        
        # Dados do escopo do plano vindos diretamente do banco temporário
        p_data_ini = dados_pag_temp.get("data_ini")
        p_data_fim = dados_pag_temp.get("data_fim")
        p_zap = dados_pag_temp.get("zap_ativo")
        p_email = dados_pag_temp.get("email_ativo")
        
        # 2. RECUPERAÇÃO DE INFORMAÇÕES CADASTRUTURAIS DO USUÁRIO
        res_user_atual = supabase.table("usuarios")\
            .select("vencimento, id, nome, email, zap_ativo")\
            .eq("id", uid_usuario)\
            .execute()
            
        if not res_user_atual.data:
            return None
            
        user_db = res_user_atual.data[0]
        
        # 3. TRATAMENTO DO VENCIMENTO DA ASSINATURA GERAL
        if tipo_renov_escolhido and "12" in str(tipo_renov_escolhido):
            meses_comprados = 12
        elif tipo_renov_escolhido and "6" in str(tipo_renov_escolhido):
            meses_comprados = 6
        elif tipo_renov_escolhido and "36" in str(tipo_renov_escolhido):
            meses_comprados = 36
        else:
            meses_comprados = 12 if valor_esperado > 150.00 else (6 if valor_esperado > 50.00 else 1)
            
        nova_data_vencimento_str = (hoje_br + relativedelta(months=meses_comprados)).strftime("%Y-%m-%d")
        
        # 4. 🚀 SALVAMENTO DIRETO E EXPLICÍTICO NA CONFIG_PROJETOS (SEM PAYLOADS EXTERNOS)
        if nome_plano:
            try:
                v_data_ini_final = p_data_ini if p_data_ini else hoje_string

                # 🔍 PASSO A: Verifica se o plano já existe para o usuário
                checagem = supabase.table("config_projetos")\
                    .select("id")\
                    .eq("projeto_id", nome_plano)\
                    .eq("usuario_id", uid_usuario)\
                    .execute()

                # 🟢 PASSO B: Se o plano JÁ EXISTIR, fazemos um UPDATE direto no ID dele
                if checagem.data:
                    id_existente = checagem.data[0]["id"]
                    supabase.table("config_projetos").update({
                        "data_ini": v_data_ini_final,
                        "data_fim": p_data_fim,
                        "zap_ativo": p_zap,
                        "email_ativo": p_email
                    }).eq("id", id_existente).execute()
                
                # 🔵 PASSO C: Se o plano NÃO EXISTIR, fazemos um INSERT limpo
                else:
                    supabase.table("config_projetos").insert({
                        "projeto_id": nome_plano,
                        "usuario_id": uid_usuario,
                        "data_ini": v_data_ini_final,
                        "data_fim": p_data_fim,
                        "zap_ativo": p_zap,
                        "email_ativo": p_email
                    }).execute()
                
                # Limpa lançamentos fora do limite de vigência do plano
                if p_data_fim:
                    supabase.table("lancamentos").delete().eq("projeto_id", nome_plano).eq("usuario_id", uid_usuario).gt("data", p_data_fim).execute()
                    
            except Exception as erro_plano:
                st.error(f"Erro ao persistir configuração do plano oficial: {erro_plano}")

        # ==============================================================================
        # 5. 🚀 ATUALIZAÇÃO DA TABELA usuarios (ÚNICO COMANDO, CAMPOS EXPLICITADOS DIRETO)
        # ==============================================================================
        try:
            supabase.table("usuarios").update({
                "vencimento": nova_data_vencimento_str,
                "data_ult_assinat": hoje_string,
                "valor_pago": float(valor_esperado),
                "tipo_renovacao": tipo_renov_escolhido
            }).eq("id", uid_usuario).execute()
            
        except Exception as erro_usuario:
            st.error(f"Erro ao atualizar dados cadastrais do usuário: {erro_usuario}")

        # 6. 🔒 ENCERRAMENTO DA TRANSAÇÃO: Muda o status para concluído
        try:
            supabase.table("pagamentos_temp").update({"status": "concluido"}).eq("pref_id", pref_id_original).execute()
        except: 
            pass
            
        # 7. 🧹 MANUTENÇÃO PREVENTIVA: Deleta os registros antigos 'concluido' deste usuário
        try:
            supabase.table("pagamentos_temp").delete().eq("usuario_id", uid_usuario).eq("status", "concluido").execute()
        except:
            pass
        
        # 8. RETORNA O DICIONÁRIO DE LOGIN COM O PLANO ATUALIZADO CARREGADO
        return {
            "id": user_db["id"],
            "nome": user_db["nome"],
            "email": user_db["email"],
            "vencimento": nova_data_vencimento_str,
            "zap_ativo": p_zap, 
            "projeto_ativo": nome_plano
        }

    except Exception as e:
        st.error(f"Erro crítico no processamento do retorno: {e}")
        return None