import streamlit as st
from datetime import datetime
import zoneinfo
from dateutil.relativedelta import relativedelta

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno de pagamento utilizando estritamente o núcleo de lógica 
    testado no script isolado (leeatu.py).
    """
    # 🌎 Configuração básica de datas recomendada para o fluxo de produção
    fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje_br = datetime.now(fuso_br).date()
    hoje_string = hoje_br.strftime('%Y-%m-%d')

    try:
        # ==============================================================================
        # 1. LEITURA DO REGISTRO TEMPORÁRIO (Núcleo do leeatu adaptado dinamicamente)
        # ==============================================================================
        # Buscamos o registro usando o pref_id que veio da URL
        res_temp = supabase.table("pagamentos_temp")\
            .select("usuario_id, valor, pref_id, projeto_id, tipo_renovacao, data_ini, data_fim, zap_ativo, email_ativo")\
            .eq("pref_id", str(pref_id))\
            .limit(1)\
            .execute()
            
        # Contingência mínima: se não achar por pref_id, tenta pelo usuário da sessão atual
        if not res_temp.data and "usuario_id" in st.session_state:
            res_temp = supabase.table("pagamentos_temp")\
                .select("usuario_id, valor, pref_id, projeto_id, tipo_renovacao, data_ini, data_fim, zap_ativo, email_ativo")\
                .eq("usuario_id", st.session_state.usuario_id)\
                .limit(1)\
                .execute()

        if not res_temp.data:
            return None
            
        # Decomposição campo a campo idêntica ao leeatu
        dados_frescos = res_temp.data[0]
        uid_usuario = dados_frescos.get("usuario_id")
        v_projeto_id = dados_frescos.get("projeto_id")
        v_tipo_renovacao = dados_frescos.get("tipo_renovacao")
        valor_pago = dados_frescos.get("valor", 0.0)
        
        v_data_ini = dados_frescos.get("data_ini")
        v_data_fim = dados_frescos.get("data_fim")
        v_zap_ativo = dados_frescos.get("zap_ativo")
        v_email_ativo = dados_frescos.get("email_ativo")
        
        # Se por algum motivo a data_ini veio vazia da temporária, assume o dia de hoje
        if not v_data_ini:
            v_data_ini = hoje_string

        # ==============================================================================
        # 2. ATUALIZAÇÃO DA TABELA config_projetos (Núcleo do leeatu puro)
        # ==============================================================================
        if v_projeto_id and uid_usuario:
            supabase.table("config_projetos").update({
                "data_ini": v_data_ini,
                "data_fim": v_data_fim,
                "zap_ativo": v_zap_ativo,
                "email_ativo": v_email_ativo
            }).eq("projeto_id", v_projeto_id).eq("usuario_id", uid_usuario).execute()

        # ==============================================================================
        # 3. ATUALIZAÇÃO DA TABELA usuarios (Núcleo do leeatu expandido com dados vitais)
        # ==============================================================================
        if uid_usuario:
            # Cálculo dinâmico de meses para a renovação da assinatura geral
            meses_comprados = 12
            if v_tipo_renovacao and "6" in str(v_tipo_renovacao):
                meses_comprados = 6
            elif v_tipo_renovacao and "36" in str(v_tipo_renovacao):
                meses_comprados = 36
            elif valor_pago and valor_pago < 100.00:
                meses_comprados = 6

            nova_data_vencimento = (hoje_br + relativedelta(months=meses_comprados)).strftime("%Y-%m-%d")

            # Atualização estrita dos campos da assinatura e do tipo_renovacao do leeatu
            supabase.table("usuarios").update({
                "vencimento": nova_data_vencimento,
                "data_ult_assinat": hoje_string,
                "valor_pago": float(valor_pago) if valor_pago else 0.0,
                "tipo_renovacao": v_tipo_renovacao
            }).eq("id", uid_usuario).execute()

        # ==============================================================================
        # 4. RETORNO ESTRUTURADO DE LOGIN PARA O FLUXO PRINCIPAL
        # ==============================================================================
        # Buscamos os dados atualizados para alimentar o st.session_state do arquivo principal
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
        st.error(f"🚨 Erro no processamento do retorno: {e}")
        return None