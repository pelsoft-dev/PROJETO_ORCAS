import streamlit as st
from datetime import datetime
import zoneinfo
from dateutil.relativedelta import relativedelta

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno mapeando estritamente os dados validados no script de teste,
    garantindo que variáveis nulas não quebrem a atualização no banco.
    """
    fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje_br = datetime.now(fuso_br).date()
    hoje_string = hoje_br.strftime('%Y-%m-%d')

    # Identificação do usuário logado na sessão
    uid_usuario = st.session_state.get("usuario_id")
    
    if not uid_usuario:
        return None

    try:
        # ==============================================================================
        # 1. BUSCA DIRECIONADA DO REGISTRO TEMPORÁRIO
        # ==============================================================================
        res_temp = supabase.table("pagamentos_temp")\
            .select("usuario_id, valor, projeto_id, tipo_renovacao, data_ini, data_fim, zap_ativo, email_ativo")\
            .eq("usuario_id", uid_usuario)\
            .limit(1)\
            .execute()
            
        if not res_temp.data:
            return None
            
        dados_frescos = res_temp.data[0]
        
        # Coleta das variáveis usando fallback explícito caso venham nulas
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
        # 2. 🚀 ATUALIZAÇÃO DA TABELA config_projetos (DIRETA E CONDICIONAL)
        # ==============================================================================
        # Só executa o update se v_projeto_id for uma string válida (evita passar None no .eq)
        if v_projeto_id and str(v_projeto_id).strip():
            supabase.table("config_projetos").update({
                "data_ini": v_data_ini,
                "data_fim": v_data_fim,
                "zap_ativo": v_zap_ativo,
                "email_ativo": v_email_ativo
            }).eq("projeto_id", str(v_projeto_id).strip()).eq("usuario_id", uid_usuario).execute()

        # ==============================================================================
        # 3. 🚀 ATUALIZAÇÃO DA TABELA usuarios (SEPARADA PARA FORÇAR GRAVAÇÃO)
        # ==============================================================================
        # Cálculo dos meses de vigência da assinatura
        meses_comprados = 12
        if v_tipo_renovacao and "6" in str(v_tipo_renovacao):
            meses_comprados = 6
        elif v_tipo_renovacao and "36" in str(v_tipo_renovacao):
            meses_comprados = 36
        elif valor_pago and valor_pago < 100.00:
            meses_comprados = 6

        nova_data_vencimento = (hoje_br + relativedelta(months=meses_comprados)).strftime("%Y-%m-%d")

        # PASSO A: Atualiza os dados cadastrais e financeiros padrão
        supabase.table("usuarios").update({
            "vencimento": nova_data_vencimento,
            "data_ult_assinat": hoje_string,
            "valor_pago": float(valor_pago) if valor_pago else 0.0
        }).eq("id", uid_usuario).execute()

        # PASSO B: Atualiza o tipo_renovacao de forma dedicada garantindo que o valor exista
        if v_tipo_renovacao:
            supabase.table("usuarios").update({
                "tipo_renovacao": str(v_tipo_renovacao)
            }).eq("id", uid_usuario).execute()

        # ==============================================================================
        # 4. RETORNO PARA FLUXO DE LOGIN
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