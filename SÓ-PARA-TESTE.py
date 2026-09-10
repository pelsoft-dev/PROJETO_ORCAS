import streamlit as st
from datetime import datetime
import zoneinfo
from dateutil.relativedelta import relativedelta

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno utilizando a lógica de correspondência exata por plano
    e centraliza o campo 'ult_valor_mensal' na tabela de usuários.
    """
    fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje_br = datetime.now(fuso_br).date()
    hoje_string = hoje_br.strftime('%Y-%m-%d')

    uid_usuario = st.session_state.get("usuario_id")
    plano_sessao = st.session_state.get("projeto_ativo")
    
    if not uid_usuario:
        return None

    try:
        # Busca a transação temporária gravada na Gestão
        query_temp = supabase.table("pagamentos_temp").select(
            "usuario_id, valor, projeto_id, tipo_renovacao, data_ini, data_fim, zap_ativo, email_ativo, ult_valor_mensal"
        )
        
        if plano_sessao:
            res_temp = query_temp.eq("projeto_id", plano_sessao).limit(1).execute()
        else:
            res_temp = query_temp.eq("usuario_id", uid_usuario).limit(1).execute()
            
        if not res_temp.data:
            return None
            
        dados_frescos = res_temp.data[0]
        
        v_projeto_id = dados_frescos.get("projeto_id")
        v_tipo_renovacao = dados_frescos.get("tipo_renovacao")
        valor_pago = dados_frescos.get("valor", 0.0)
        
        v_data_ini = dados_frescos.get("data_ini")
        v_data_fim = dados_frescos.get("data_fim")
        v_zap_ativo = dados_frescos.get("zap_ativo")
        v_email_ativo = dados_frescos.get("email_ativo")
        v_ult_valor_mensal = dados_frescos.get("ult_valor_mensal", 0.0)

        # -----------------------------------------------------------------
        # CORREÇÃO PRINCIPAL: Usar UPSERT para CRIAR o plano se for novo
        # ou ATUALIZAR se já existir.
        # -----------------------------------------------------------------
        dados_plano_upsert = {
            "usuario_id": uid_usuario,
            "projeto_id": v_projeto_id,
            "data_ini": v_data_ini,
            "data_fim": v_data_fim,
            "zap_ativo": 1 if v_zap_ativo else 0,
            "email_ativo": 1 if v_email_ativo else 0
        }

        # Se o plano já existia, recupera o ID para manter consistência
        res_p = supabase.table("config_projetos").select("id").eq("projeto_id", v_projeto_id).eq("usuario_id", uid_usuario).execute()
        if res_p and hasattr(res_p, 'data') and res_p.data:
            dados_plano_upsert["id"] = res_p.data[0]["id"]

        # Grava efetivamente o plano no Supabase
        supabase.table("config_projetos").upsert(dados_plano_upsert).execute()

        # Cálculo das datas comerciais de renovação da assinatura do usuário
        meses_comprados = 12
        if v_tipo_renovacao and "6" in str(v_tipo_renovacao):
            meses_comprados = 6
        elif v_tipo_renovacao and "36" in str(v_tipo_renovacao):
            meses_comprados = 36
        elif valor_pago and valor_pago < 100.00:
            meses_comprados = 6

        nova_data_vencimento = (hoje_br + relativedelta(months=meses_comprados)).strftime("%Y-%m-%d")

        # Atualiza o cadastro do usuário
        supabase.table("usuarios").update({
            "vencimento": nova_data_vencimento,
            "data_ult_assinat": hoje_string,
            "valor_pago": float(valor_pago) if valor_pago else 0.0,
            "ult_valor_mensal": float(v_ult_valor_mensal) if v_ult_valor_mensal else 0.0,
            "tipo_renovacao": v_tipo_renovacao
        }).eq("id", uid_usuario).execute()

        # Limpa o registro temporário pois a operação foi concluída com sucesso
        supabase.table("pagamentos_temp").delete().eq("usuario_id", str(uid_usuario).strip()).execute()

        # Retorna os dados para login/redirecionamento no orcasapp
        res_user_final = supabase.table("usuarios").select("id, nome, email, vencimento").eq("id", uid_usuario).execute()
        if res_user_final.data:
            u = res_user_final.data[0]
            return {
                "id": u["id"],
                "nome": u["nome"],
                "email": u["email"],
                "vencimento": u["vencimento"],
                "zap_ativo": v_zap_ativo,
                "projeto_ativo": v_projeto_id
            }
        return None
            
    except Exception as e:
        st.error(f"Erro no processamento do retorno: {e}")
        return None