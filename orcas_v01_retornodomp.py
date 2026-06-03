import streamlit as st
from datetime import datetime
import zoneinfo
from dateutil.relativedelta import relativedelta

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno de pagamento utilizando estritamente o núcleo de lógica 
    do leeatu, baseando a busca principal no usuario_id.
    """
    # 🌎 Configuração básica de datas recomendada para o fluxo
    fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje_br = datetime.now(fuso_br).date()
    hoje_string = hoje_br.strftime('%Y-%m-%d')

    # Identifica o usuário logado diretamente pela sessão do Streamlit
    uid_usuario = st.session_state.get("usuario_id")
    
    if not uid_usuario:
        return None

    try:
        # ==============================================================================
        # 1. LEITURA DO REGISTRO TEMPORÁRIO (Núcleo do leeatu baseado no usuario_id)
        # ==============================================================================
        # Forçamos o select a trazer apenas as colunas existentes, evitando conflito com metadados
        res_temp = supabase.table("pagamentos_temp")\
            .select("usuario_id, valor, projeto_id, tipo_renovacao, data_ini, data_fim, zap_ativo, email_ativo")\
            .eq("usuario_id", uid_usuario)\
            .limit(1)\
            .execute()
            
        if not res_temp.data:
            return None
            
        # Extração das variáveis locais idêntica ao script leeatu
        dados_frescos = res_temp.data[0]
        v_projeto_id = dados_frescos.get("projeto_id")
        v_tipo_renovacao = dados_frescos.get("tipo_renovacao")
        valor_pago = dados_frescos.get("valor", 0.0)
        
        v_data_ini = dados_frescos.get("data_ini")
        v_data_fim = dados_frescos.get("data_fim")
        v_zap_ativo = dados_frescos.get("zap_ativo")
        v_email_ativo = dados_frescos.get("email_ativo")
        
        if not v_data_ini:
            v_data_ini = hoje_string

        # ==============================================================================
        # 2. ATUALIZAÇÃO DA TABELA config_projetos (Núcleo do leeatu puro)
        # ==============================================================================
        if v_projeto_id:
            supabase.table("config_projetos").update({
                "data_ini": v_data_ini,
                "data_fim": v_data_fim,
                "zap_ativo": v_zap_ativo,
                "email_ativo": v_email_ativo
            }).eq("projeto_id", v_projeto_id).eq("usuario_id", uid_usuario).execute()

        # ==============================================================================
        # 3. ATUALIZAÇÃO DA TABELA usuarios (Núcleo do leeatu unificado e expandido)
        # ==============================================================================
        # Cálculo dinâmico da nova data de vencimento
        meses_comprados = 12
        if v_tipo_renovacao and "6" in str(v_tipo_renovacao):
            meses_comprados = 6
        elif v_tipo_renovacao and "36" in str(v_tipo_renovacao):
            meses_comprados = 36
        elif valor_pago and valor_pago < 100.00:
            meses_comprados = 6

        nova_data_vencimento = (hoje_br + relativedelta(months=meses_comprados)).strftime("%Y-%m-%d")

        # Injeta todos os campos de uma só vez para garantir consistência atômica no banco
        supabase.table("usuarios").update({
            "vencimento": nova_data_vencimento,
            "data_ult_assinat": hoje_string,
            "valor_pago": float(valor_pago) if valor_pago else 0.0,
            "tipo_renovacao": v_tipo_renovacao
        }).eq("id", uid_usuario).execute()

        # ==============================================================================
        # 4. RETORNO ESTRUTURADO PARA O FLUXO PRINCIPAL
        # ==============================================================================
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