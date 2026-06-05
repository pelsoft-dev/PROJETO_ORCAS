import streamlit as st
from datetime import datetime
import zoneinfo
from dateutil.relativedelta import relativedelta

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Lógica direta focada na limpeza absoluta das strings para correspondência no Supabase.
    """
    fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje_br = datetime.now(fuso_br).date()
    hoje_string = hoje_br.strftime('%Y-%m-%d')

    uid_usuario = st.session_state.get("usuario_id")
    if not uid_usuario:
        return None

    try:
        # 1. LEITURA DOS DADOS TEMPORÁRIOS
        res_temp = supabase.table("pagamentos_temp")\
            .select("usuario_id, valor, projeto_id, tipo_renovacao, data_ini, data_fim, zap_ativo, email_ativo")\
            .eq("usuario_id", uid_usuario)\
            .limit(1)\
            .execute()
            
        if not res_temp.data:
            return None
            
        dados = res_temp.data[0]
        
        # Forçando strings limpas sem espaços invisíveis que quebram o .eq() do Supabase
        v_projeto_id = str(dados.get("projeto_id")).strip() if dados.get("projeto_id") else None
        v_tipo_renovacao = str(dados.get("tipo_renovacao")).strip() if dados.get("tipo_renovacao") else None
        valor_pago = dados.get("valor", 0.0)
        
        v_data_ini = dados.get("data_ini") if dados.get("data_ini") else hoje_string
        v_data_fim = dados.get("data_fim")
        v_zap_ativo = dados.get("zap_ativo")
        v_email_ativo = dados.get("email_ativo")

        # 2. ATUALIZAÇÃO DA TABELA config_projetos
        # Se o projeto ID existir, rodamos o update filtrando estritamente por ele
        if v_projeto_id:
            supabase.table("config_projetos").update({
                "data_ini": v_data_ini,
                "data_fim": v_data_fim,
                "zap_ativo": v_zap_ativo,
                "email_ativo": v_email_ativo
            }).eq("usuario_id", uid_usuario).eq("projeto_id", v_projeto_id).execute()

        # 3. ATUALIZAÇÃO DA TABELA usuarios
        meses_comprados = 12
        if v_tipo_renovacao and "6" in v_tipo_renovacao:
            meses_comprados = 6
        elif v_tipo_renovacao and "36" in v_tipo_renovacao:
            meses_comprados = 36
        elif valor_pago and valor_pago < 100.00:
            meses_comprados = 6

        nova_data_vencimento = (hoje_br + relativedelta(months=meses_comprados)).strftime("%Y-%m-%d")

        # Forçando a gravação de todos os parâmetros em formato primitivo
        supabase.table("usuarios").update({
            "vencimento": str(nova_data_vencimento),
            "data_ult_assinat": str(hoje_string),
            "valor_pago": float(valor_pago) if valor_pago else 0.0,
            "tipo_renovacao": v_tipo_renovacao  # Garantido como string limpa ou None
        }).eq("id", uid_usuario).execute()

        # 4. RETORNO DE CONFIGURAÇÃO DE SESSÃO
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