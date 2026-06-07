import streamlit as st
from datetime import datetime
import zoneinfo
from dateutil.relativedelta import relativedelta

def tratar_retorno(supabase, pref_id, status_retorno, uid_forcado=None, valor_forcado=None):
    fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje_br = datetime.now(fuso_br).date()
    hoje_string = hoje_br.strftime('%Y-%m-%d')

    # Se veio pelo bypass, usa o ID forçado. Se não, pega da sessão.
    uid_usuario = uid_forcado if uid_forcado else st.session_state.get("usuario_id")
    
    if not uid_usuario:
        return None

    uid_usuario = str(uid_usuario).strip()

    try:
        # Busca os dados que você salvou lá na tela de gestão antes de ir pro MP
        res_temp = supabase.table("pagamentos_temp").select("*").eq("usuario_id", uid_usuario).limit(1).execute()
            
        if not res_temp.data:
            return None
            
        dados_frescos = res_temp.data[0]
        
        v_projeto_id = dados_frescos.get("projeto_id")
        v_tipo_renovacao = dados_frescos.get("tipo_renovacao")
        # Usa o valor real pago (ou o forçado do bypass)
        valor_pago = valor_forcado if valor_forcado else dados_frescos.get("valor", 0.0)
        
        v_data_ini = dados_frescos.get("data_ini")
        v_data_fim = dados_frescos.get("data_fim")
        v_zap_ativo = dados_frescos.get("zap_ativo")
        v_email_ativo = dados_frescos.get("email_ativo")

        # 1. ATUALIZA OS PROJETOS
        if v_projeto_id:
            supabase.table("config_projetos").update({
                "data_ini": v_data_ini,
                "data_fim": v_data_fim,
                "zap_ativo": v_zap_ativo,
                "email_ativo": v_email_ativo
            }).eq("projeto_id", v_projeto_id).eq("usuario_id", uid_usuario).execute()

        # 2. CALCULA O VENCIMENTO COM BASE NO TIPO DE RENOVAÇÃO
        meses_comprados = 12
        if v_tipo_renovacao and "6" in str(v_tipo_renovacao):
            meses_comprados = 6
        elif v_tipo_renovacao and "36" in str(v_tipo_renovacao):
            meses_comprados = 36
        elif float(valor_pago) < 100.00:
            meses_comprados = 6

        nova_data_vencimento = (hoje_br + relativedelta(months=meses_comprados)).strftime("%Y-%m-%d")

        # 3. ATUALIZA O USUÁRIO COMPLETO (INCLUINDO TIPO_RENOVACAO)
        supabase.table("usuarios").update({
            "vencimento": nova_data_vencimento,
            "data_ult_assinat": hoje_string,
            "valor_pago": float(valor_pago),
            "tipo_renovacao": v_tipo_renovacao # Grava os 48 meses aqui!
        }).eq("id", uid_usuario).execute()

        # 🔥 4. LIMPEZA TOTAL DA TABELA TEMPORÁRIA (SÓ AQUI E EM MAIS NENHUM LUGAR)
        supabase.table("pagamentos_temp").delete().eq("usuario_id", uid_usuario).execute()

        # 5. RETORNA OS DADOS PARA MONTAR A SESSÃO LOGADA
        res_user_final = supabase.table("usuarios").select("id, nome, email, vencimento").eq("id", uid_usuario).execute()
        if res_user_final.data:
            u = res_user_final.data[0]
            return {
                "id": u["id"],
                "nome": u["nome"],
                "email": u["email"],
                "vencimento": u["vencimento"],
                "zap_ativo": v_zap_ativo,
                "projeto_ativo": v_projeto_id,
                "email_ativo": v_email_ativo
            }
        return None
            
    except Exception as e:
        st.error(f"Erro no processamento do retorno: {e}")
        return None