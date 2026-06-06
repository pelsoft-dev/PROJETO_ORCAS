import streamlit as st
from datetime import datetime
import zoneinfo
from dateutil.relativedelta import relativedelta

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno utilizando a lógica de correspondência exata por plano
    validada no script leeatu.py.
    """
    fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje_br = datetime.now(fuso_br).date()
    hoje_string = hoje_br.strftime('%Y-%m-%d')

    uid_usuario = st.session_state.get("usuario_id")
    # Captura o plano ativo na sessão (Equivalente ao 'planoaserlido' do leeatu)
    plano_sessao = st.session_state.get("projeto_ativo")
    
    if not uid_usuario:
        return None

    try:
        # ==============================================================================
        # 1. BUSCA DIRECIONADA (LÓGICA IGUAL AO LEEATU.PY)
        # ==============================================================================
        # Se houver um plano na sessão, buscamos diretamente por ele para não pegar lixo
        query_temp = supabase.table("pagamentos_temp").select("usuario_id, valor, projeto_id, tipo_renovacao, data_ini, data_fim, zap_ativo, email_ativo")
        
        if plano_sessao:
            res_temp = query_temp.eq("projeto_id", plano_sessao).limit(1).execute()
        else:
            res_temp = query_temp.eq("usuario_id", uid_usuario).limit(1).execute()
            
        if not res_temp.data:
            return None
            
        dados_frescos = res_temp.data[0]
        
        # Extração idêntica de variáveis do leeatu
        v_projeto_id = dados_frescos.get("projeto_id")
        v_tipo_renovacao = dados_frescos.get("tipo_renovacao")
        valor_pago = dados_frescos.get("valor", 0.0)
        
        v_data_ini = dados_frescos.get("data_ini")
        v_data_fim = dados_frescos.get("data_fim")
        v_zap_ativo = dados_frescos.get("zap_ativo")
        v_email_ativo = dados_frescos.get("email_ativo")

        # ==============================================================================
        # 2. ATUALIZAÇÃO DA TABELA config_projetos (IGUAL AO LEEATU.PY)
        # ==============================================================================
        supabase.table("config_projetos").update({
            "data_ini": v_data_ini,
            "data_fim": v_data_fim,
            "zap_ativo": v_zap_ativo,
            "email_ativo": v_email_ativo
        }).eq("projeto_id", v_projeto_id).eq("usuario_id", uid_usuario).execute()

        # ==============================================================================
        # 3. ATUALIZAÇÃO DA TABELA usuarios (QUERY PARCIAL + CAMPO TIPO_RENOVACAO)
        # ==============================================================================
        # Cálculo das datas comerciais do fluxo oficial
        meses_comprados = 12
        if v_tipo_renovacao and "6" in str(v_tipo_renovacao):
            meses_comprados = 6
        elif v_tipo_renovacao and "36" in str(v_tipo_renovacao):
            meses_comprados = 36
        elif valor_pago and valor_pago < 100.00:
            meses_comprados = 6

        nova_data_vencimento = (hoje_br + relativedelta(months=meses_comprados)).strftime("%Y-%m-%d")

        # Primeiro atualiza os dados financeiros da transação oficial
        supabase.table("usuarios").update({
            "vencimento": nova_data_vencimento,
            "data_ult_assinat": hoje_string,
            "valor_pago": float(valor_pago) if valor_pago else 0.0
        }).eq("id", uid_usuario).execute()

        # Aplica a lógica exata do bloco IF do leeatu.py para o tipo_renovacao
        if uid_usuario and v_tipo_renovacao:
            supabase.table("usuarios").update({
                "tipo_renovacao": v_tipo_renovacao
            }).eq("id", uid_usuario).execute()

        # ==============================================================================
        # 🔥 LIMPEZA DA TABELA TEMPORÁRIA APÓS O SUCESSO (Sua nova lógica)
        # ==============================================================================
        # O fluxo funcionou, salvou tudo, então agora limpamos o registro consumido
        if uid_usuario:
            supabase.table("pagamentos_temp").delete().eq("usuario_id", str(uid_usuario).strip()).execute()

        # ==============================================================================
        # 4. RETORNO DE CONFIGURAÇÃO DE SESSÃO
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
        st.error(f"Erro no processamento do retorno: {e}")
        return None