import requests
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import streamlit as st

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno de forma resiliente: localiza o pagamento pendente do usuário,
    atualiza sua assinatura calculando o vencimento comercial correto, recupera o plano 
    ativo salvo temporariamente, limpa o registro temporário e faz o login automático.
    
    CORREÇÃO: Caso o Webhook já tenha processado e deletado o registro temporário,
    o sistema faz uma busca pela sessão ativa ou pelo status da licença do usuário para
    garantir o bypass de login sem exibir mensagens de erro/expiração.
    """
    # Aceita approved, authorized e pending (comum em fluxos PIX reais no redirecionamento)
    if status_retorno not in ["approved", "authorized", "pending"]:
        return None

    hoje = date.today()

    try:
        # 1. LOCALIZAÇÃO DO REGISTRO TEMPORÁRIO
        res_temp = supabase.table("pagamentos_temp")\
            .select("usuario_id, valor, pref_id, projeto_id, vencimento_proposto, tipo_renovacao")\
            .eq("pref_id", str(pref_id))\
            .execute()
            
        # CONTINGÊNCIA 1: Se o Webhook já processou MUITO rápido e deletou o registro,
        # verificamos se o session_state do Streamlit possui o ID e o vencimento proposto guardados
        if not res_temp.data and "alteracao_licenca_pendente" in st.session_state:
            dados_pendentes = st.session_state.alteracao_licenca_pendente
            uid_usuario = dados_pendentes["dados_projeto"]["usuario_id"]
            
            # Busca direta na tabela oficial de usuários para validar se o Webhook já o atualizou
            res_user_direto = supabase.table("usuarios")\
                .select("id, nome, email, vencimento, zap_ativo")\
                .eq("id", uid_usuario)\
                .execute()
                
            if res_user_direto.data:
                user_db = res_user_direto.data[0]
                # Se o vencimento no banco já está igual ou posterior ao proposto, o Webhook já venceu a corrida!
                if user_db["vencimento"] >= hoje.strftime("%Y-%m-%d"):
                    return {
                        "id": user_db["id"],
                        "nome": user_db["nome"],
                        "email": user_db["email"],
                        "vencimento": user_db["vencimento"],
                        "zap_ativo": user_db["zap_ativo"],
                        "projeto_id": dados_pendentes["dados_projeto"]["projeto_id"]
                    }

        # CONTINGÊNCIA 2: Se não achou na sessão nem por ID exato, tenta buscar o último do próprio usuário ativo
        if not res_temp.data and "usuario_id" in st.session_state:
            res_temp = supabase.table("pagamentos_temp")\
                .select("usuario_id, valor, pref_id, projeto_id, vencimento_proposto, tipo_renovacao")\
                .eq("usuario_id", st.session_state.usuario_id)\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()

        # Se mesmo com todas as contingências de segurança o registro sumiu e o usuário não está logado
        if not res_temp.data:
            print("Nenhum rastro de pagamento temporário localizado. Assumindo processamento prévio por Webhook.")
            # Tentativa final: Se temos o e-mail na sessão, logamos usando o estado atualizado do banco
            if st.session_state.get("usuario_email"):
                res_user_final = supabase.table("usuarios").select("*").eq("email", st.session_state.usuario_email).execute()
                if res_user_final.data:
                    u = res_user_final.data[0]
                    return {
                        "id": u["id"], "nome": u["nome"], "email": u["email"],
                        "vencimento": u["vencimento"], "zap_ativo": u.get("zap_ativo", 0),
                        "projeto_ativo": st.session_state.get("projeto_ativo")
                    }
            return None
            
        dados_pag_temp = res_temp.data[0]
        uid_usuario = dados_pag_temp["usuario_id"]
        valor_esperado = dados_pag_temp["valor"]
        pref_id_original = dados_pag_temp["pref_id"]
        plano_salvo = dados_pag_temp.get("projeto_id")
        vencimento_proposto = dados_pag_temp.get("vencimento_proposto")
        tipo_renov_escolhido = dados_pag_temp.get("tipo_renovacao")
        
        # 2. BUSCA OS DADOS DO USUÁRIO PARA ATUALIZAÇÃO
        res_user_atual = supabase.table("usuarios")\
            .select("vencimento, id, nome, email, zap_ativo")\
            .eq("id", uid_usuario)\
            .execute()
            
        if not res_user_atual.data:
            return None
            
        user_db = res_user_atual.data[0]
        
        # 3. DEFINIÇÃO DA DATA DE VENCIMENTO COMERCIAL
        # Se o painel de gestão já calculou a data ideal exata baseada em "Hoje + Período", usamos ela
        if vencimento_proposto:
            nova_data_vencimento_str = vencimento_proposto
        else:
            # Fallback de segurança caso a coluna não exista ou venha nula
            meses_comprados = 1
            if valor_esperado > 150.00:
                meses_comprados = 12
            elif valor_esperado > 50.00:
                meses_comprados = 6
                
            dt_calculada = hoje + relativedelta(months=meses_comprados)
            nova_data_vencimento_str = dt_calculada.strftime("%Y-%m-%d")
        
        # 4. ATUALIZA OS DADOS DA LICENÇA NA TABELA PRINCIPAL DE USUÁRIOS
        dados_atualizacao_usuario = {
            "vencimento": nova_data_vencimento_str,
            "data_ult_assinat": hoje.strftime("%Y-%m-%d"),
            "valor_pago": float(valor_esperado)
        }
        
        # Se veio gravado o tipo de renovação no temporário, sincroniza no cadastro do cliente
        if tipo_renov_escolhido:
            dados_atualizacao_usuario["tipo_renovacao"] = tipo_renov_escolhido

        supabase.table("usuarios").update(dados_atualizacao_usuario).eq("id", uid_usuario).execute()
        
        # 5. LIMPEZA: Remove o registro temporário para evitar duplicidades futuras
        supabase.table("pagamentos_temp")\
            .delete()\
            .eq("pref_id", pref_id_original)\
            .execute()
        
        # Limpa o estado temporário de sessão se ele existir
        if "alteracao_licenca_pendente" in st.session_state:
            del st.session_state.alteracao_licenca_pendente
        
        # 6. RETORNA O DICIONÁRIO COMPLETO PARA EFETUAR O LOGIN AUTOMÁTICO (BYPASS)
        return {
            "id": user_db["id"],
            "nome": user_db["nome"],
            "email": user_db["email"],
            "vencimento": nova_data_vencimento_str,
            "zap_ativo": user_db["zap_ativo"],
            "projeto_ativo": plano_salvo
        }

    except Exception as e:
        print(f"Erro crítico no processamento do retorno MP: {e}")
        return None