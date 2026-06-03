import streamlit as st
from datetime import datetime
import zoneinfo
from dateutil.relativedelta import relativedelta

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno mapeando estritamente os dados validados no script de teste,
    imprimindo os resultados diretamente no terminal para acompanhamento real.
    """
    fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje_br = datetime.now(fuso_br).date()
    hoje_string = hoje_br.strftime('%Y-%m-%d')

    # Identificação do usuário logado na sessão
    uid_usuario = st.session_state.get("usuario_id")
    
    if not uid_usuario:
        print("❌ [RETORNO] Execução abortada: usuario_id não encontrado na st.session_state.")
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
            print(f"⚠️ [RETORNO] Nenhum registro encontrado na 'pagamentos_temp' para o usuario_id: {uid_usuario}")
            return None
            
        dados_frescos = res_temp.data[0]
        
        # Coleta das variáveis do registro temporário
        v_projeto_id = dados_frescos.get("projeto_id")
        v_tipo_renovacao = dados_frescos.get("tipo_renovacao")
        valor_pago = dados_frescos.get("valor", 0.0)
        
        v_data_ini = dados_frescos.get("data_ini")
        v_data_fim = dados_frescos.get("data_fim")
        v_zap_ativo = dados_frescos.get("zap_ativo")
        v_email_ativo = dados_frescos.get("email_ativo")
        
        if not v_data_ini:
            v_data_ini = hoje_string

        # 🟥 EXIBIÇÃO DE CONTROLE NO TERMINAL
        print("\n=======================================================")
        print("📥 VALORES RECUPERADOS DA TABELA TEMPORÁRIA:")
        print(f" - ID do Usuário: {uid_usuario}")
        print(f" - ID do Projeto: '{v_projeto_id}'")
        print(f" - Tipo Renovação: '{v_tipo_renovacao}'")
        print(f" - Valor Pago: {valor_pago}")
        print("=======================================================\n")

        # ==============================================================================
        # 2. 🚀 ATUALIZAÇÃO DA TABELA config_projetos
        # ==============================================================================
        if v_projeto_id and str(v_projeto_id).strip():
            print(f"⏳ [CONFIG_PROJETOS] Executando update para o plano '{v_projeto_id}'...")
            res_config = supabase.table("config_projetos").update({
                "data_ini": v_data_ini,
                "data_fim": v_data_fim,
                "zap_ativo": v_zap_ativo,
                "email_ativo": v_email_ativo
            }).eq("projeto_id", str(v_projeto_id).strip()).eq("usuario_id", uid_usuario).execute()
            
            print(f"🟩 [CONFIG_PROJETOS] Retorno do banco (linhas afetadas): {res_config.data}")

        # ==============================================================================
        # 3. 🚀 ATUALIZAÇÃO DA TABELA usuarios (QUERY UNIFICADA ESTILO TESTE)
        # ==============================================================================
        meses_comprados = 12
        if v_tipo_renovacao and "6" in str(v_tipo_renovacao):
            meses_comprados = 6
        elif v_tipo_renovacao and "36" in str(v_tipo_renovacao):
            meses_comprados = 36
        elif valor_pago and valor_pago < 100.00:
            meses_comprados = 6

        nova_data_vencimento = (hoje_br + relativedelta(months=meses_comprados)).strftime("%Y-%m-%d")

        print(f"⏳ [USUARIOS] Gravando dados e tipo_renovacao '{v_tipo_renovacao}'...")
        
        # Enviando todos os campos de uma vez só na mesma transação
        res_user = supabase.table("usuarios").update({
            "vencimento": nova_data_vencimento,
            "data_ult_assinat": hoje_string,
            "valor_pago": float(valor_pago) if valor_pago else 0.0,
            "tipo_renovacao": v_tipo_renovacao
        }).eq("id", uid_usuario).execute()
        
        print(f"🟩 [USUARIOS] Retorno do banco (linhas afetadas): {res_user.data}")

        # ==============================================================================
        # 4. RETORNO PARA FLUXO DE LOGIN
        # ==============================================================================
        res_user_final = supabase.table("usuarios").select("id, nome, email, vencimento").eq("id", uid_usuario).execute()
        
        if res_user_final.data:
            u = res_user_final.data[0]
            print("✅ [RETORNO] Processamento concluído com sucesso total.")
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
        print(f"🚨 [RETORNO] ERRO CRÍTICO CAPTURADO NO TERMINAL: {e}")
        st.error(f"🚨 Erro no processamento do retorno: {e}")
        return None