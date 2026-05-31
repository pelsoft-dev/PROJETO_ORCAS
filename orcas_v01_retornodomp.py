import requests
from datetime import datetime
import zoneinfo
from dateutil.relativedelta import relativedelta
import streamlit as st

def tratar_retorno(supabase, pref_id, status_retorno):
    st.info(f"🔍 [LOG 1] Função chamada! pref_id: {pref_id} | status: {status_retorno}")
    
    if status_retorno not in ["approved", "authorized", "pending"]:
        st.warning(f"⚠️ [LOG 2] Status inválido recebido: {status_retorno}")
        return None

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
            
        st.info(f"🔍 [LOG 3] Resultado da busca por pref_id: {res_temp.data}")
            
        if not res_temp.data and "usuario_id" in st.session_state:
            st.info(f"🔍 [LOG 4] Tentando buscar pelo ID do usuário da sessão: {st.session_state.usuario_id}")
            res_temp = supabase.table("pagamentos_temp")\
                .select("usuario_id, valor, pref_id, projeto_id, tipo_renovacao, data_ini, data_fim, zap_ativo, email_ativo")\
                .eq("usuario_id", st.session_state.usuario_id)\
                .eq("status", "aguardando")\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()
            st.info(f"🔍 [LOG 5] Resultado da busca secundária: {res_temp.data}")

        if not res_temp.data:
            st.error("🚨 [LOG 6] NENHUM dado encontrado em pagamentos_temp com status 'aguardando'. Saindo da função.")
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
        
        p_data_ini = dados_pag_temp.get("data_ini")
        p_data_fim = dados_pag_temp.get("data_fim")
        p_zap = dados_pag_temp.get("zap_ativo")
        p_email = dados_pag_temp.get("email_ativo")
        
        st.success(f"✅ [LOG 7] Dados recuperados da temporária! Preparando payload para projeto: {nome_plano}")
        
        # 2. RECUPERAÇÃO DE INFORMAÇÕES CADASTRUTURAIS
        res_user_atual = supabase.table("usuarios").select("vencimento, id, nome, email, zap_ativo").eq("id", uid_usuario).execute()
        user_db = res_user_atual.data[0]
        
        # 3. TRATAMENTO DO VENCIMENTO
        if tipo_renov_escolhido and "12" in str(tipo_renov_escolhido):
            meses_comprados = 12
        elif tipo_renov_escolhido and "6" in str(tipo_renov_escolhido):
            meses_comprados = 6
        elif tipo_renov_escolhido and "36" in str(tipo_renov_escolhido):
            meses_comprados = 36
        else:
            meses_comprados = 12 if valor_esperado > 150.00 else (6 if valor_esperado > 50.00 else 1)
            
        nova_data_vencimento_str = (hoje_br + relativedelta(months=meses_comprados)).strftime("%Y-%m-%d")
        
        # 4. SALVAMENTO NA CONFIG_PROJETOS
        if nome_plano:
            res_projeto_oficial = supabase.table("config_projetos").select("id").eq("projeto_id", nome_plano).eq("usuario_id", uid_usuario).execute()
            
            payload_plano = {
                "projeto_id": nome_plano,
                "usuario_id": uid_usuario,
                "data_ini": p_data_ini if p_data_ini else hoje_string,
                "data_fim": p_data_fim,
                "zap_ativo": p_zap,
                "email_ativo": p_email
            }
            
            if res_projeto_oficial.data:
                payload_plano["id"] = res_projeto_oficial.data[0]["id"]
            
            st.info(f"🚀 [LOG 8] Enviando Upsert para config_projetos: {payload_plano}")
            __ret = supabase.table("config_projetos").upsert(payload_plano).execute()
            st.success(f"✅ [LOG 9] Resposta do Upsert: {__ret.data}")

        # 5. ATUALIZA USUÁRIO
        supabase.table("usuarios").update({"vencimento": nova_data_vencimento_str, "data_ult_assinat": hoje_string, "valor_pago": float(valor_esperado)}).eq("id", uid_usuario).execute()
        
        # 6. ATUALIZA TEMPORÁRIA
        supabase.table("pagamentos_temp").update({"status": "concluido"}).eq("pref_id", pref_id_original).execute()
        st.success("🎉 [LOG 10] Tudo finalizado com sucesso!")
        
        return {
            "id": user_db["id"], "nome": user_db["nome"], "email": user_db["email"],
            "vencimento": nova_data_vencimento_str, "zap_ativo": p_zap, "projeto_ativo": nome_plano
        }

    except Exception as e:
        st.error(f"❌ [ERRO CRÍTICO] Falha na função tratar_retorno: {e}")
        return None