import requests
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import streamlit as st

def tratar_retorno(supabase, pref_id, status_retorno):
    """
    Processa o retorno de forma resiliente: localiza o pagamento pendente do usuário,
    atualiza sua assinatura calculando o vencimento comercial correto, recupera o plano 
    ativo salvo temporariamente, efetua o salvamento das novas configurações do plano (ex: 36 meses, e-mail),
    limpa o registro temporário e faz o login automático.
    """
    if status_retorno not in ["approved", "authorized", "pending"]:
        return None

    hoje = date.today()

    try:
        # 1. LOCALIZAÇÃO DO REGISTRO TEMPORÁRIO
        res_temp = supabase.table("pagamentos_temp")\
            .select("usuario_id, valor, pref_id, projeto_id, vencimento_proposto, tipo_renovacao")\
            .eq("pref_id", str(pref_id))\
            .execute()
            
        # CONTINGÊNCIA 1: Caso o Webhook já tenha processado rápido demais e apagado o registro
        if not res_temp.data and "alteracao_licenca_pendente" in st.session_state:
            dados_pendentes = st.session_state.alteracao_licenca_pendente
            uid_usuario = dados_pendentes["dados_projeto"]["usuario_id"]
            
            res_user_direto = supabase.table("usuarios")\
                .select("id, nome, email, vencimento, zap_ativo")\
                .eq("id", uid_usuario)\
                .execute()
                
            if res_user_direto.data:
                user_db = res_user_direto.data[0]
                if user_db["vencimento"] >= hoje.strftime("%Y-%m-%d"):
                    return {
                        "id": user_db["id"],
                        "nome": user_db["nome"],
                        "email": user_db["email"],
                        "vencimento": user_db["vencimento"],
                        "zap_ativo": user_db["zap_ativo"],
                        "projeto_ativo": dados_pendentes["dados_projeto"]["projeto_id"]
                    }

        # CONTINGÊNCIA 2: Busca retroativa baseada na sessão ativa
        if not res_temp.data and "usuario_id" in st.session_state:
            res_temp = supabase.table("pagamentos_temp")\
                .select("usuario_id, valor, pref_id, projeto_id, vencimento_proposto, tipo_renovacao")\
                .eq("usuario_id", st.session_state.usuario_id)\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()

        # Fallback definitivo de emergência por e-mail
        if not res_temp.data:
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
        
        # 2. RECUPERAÇÃO DE INFORMAÇÕES DO USUÁRIO
        res_user_atual = supabase.table("usuarios")\
            .select("vencimento, id, nome, email, zap_ativo")\
            .eq("id", uid_usuario)\
            .execute()
            
        if not res_user_atual.data:
            return None
            
        user_db = res_user_atual.data[0]
        
        # 3. TRATAMENTO DO NOVO VENCIMENTO DA ASSINATURA
        if vencimento_proposto:
            nova_data_vencimento_str = vencimento_proposto
        else:
            meses_comprados = 1
            if valor_esperado > 150.00: meses_comprados = 12
            elif valor_esperado > 50.00: meses_comprados = 6
                
            nova_data_vencimento_str = (hoje + relativedelta(months=meses_comprados)).strftime("%Y-%m-%d")

        # 4. 🚀 CONSOLIDAR AS ALTERAÇÕES DO PLANO DE LICENÇA (Sincronização Real)
        if plano_salvo:
            try:
                # Verifica se a string contém o caractere delimitador pipeline '|'
                if "|" in str(plano_salvo):
                    # Decodifica a string compactada guardada na ida
                    partes = str(plano_salvo).split("|")
                    nome_real_plano = partes[0]
                    meses_escolhidos = int(partes[1])
                    zap_status = int(partes[2])
                    email_status = int(partes[3])
                else:
                    # Fallback clássico caso venha apenas o nome puro
                    nome_real_plano = plano_salvo
                    meses_escolhidos = 36 if valor_esperado > 50.00 else 24
                    zap_status = 0
                    email_status = 1

                # Redefine o nome real do plano para ser devolvido corretamente ao sistema
                plano_salvo = nome_real_plano 

                # Busca o histórico do projeto oficial para herdar metadados ou ID existente
                res_projeto_oficial = supabase.table("config_projetos").select("*").eq("projeto_id", nome_real_plano).eq("usuario_id", uid_usuario).execute()
                
                # Define a data de início (padrão dia 1 do mês atual)
                data_ini_calc = hoje.replace(day=1).strftime("%Y-%m-%d")
                if res_projeto_oficial.data:
                    data_ini_calc = res_projeto_oficial.data[0].get("data_ini", data_ini_calc)
                
                # Calcula a nova data fim somando rigorosamente os meses escolhidos pelo slider (ex: 36 meses)
                dt_ini_parsed = datetime.strptime(data_ini_calc, "%Y-%m-%d").date()
                dt_fim_calculada = (dt_ini_parsed + relativedelta(months=meses_escolhidos - 1))
                data_fim_calc = (dt_fim_calculada.replace(day=1) + relativedelta(months=1, days=-1)).strftime("%Y-%m-%d")
                
                payload_plano = {
                    "projeto_id": nome_real_plano,
                    "usuario_id": uid_usuario,
                    "data_ini": data_ini_calc,
                    "data_fim": data_fim_calc,
                    "zap_ativo": zap_status,
                    "email_ativo": email_status
                }
                
                # Evita duplicidades ou restrições de chave única anexando o ID caso o plano já existisse
                if res_projeto_oficial.data:
                    payload_plano["id"] = res_projeto_oficial.data[0]["id"]
                
                # Salva de forma definitiva as alterações calculadas na tabela config_projetos
                supabase.table("config_projetos").upsert(payload_plano).execute()
                
                # Remove limpezas futuras incoerentes com o novo prazo estendido
                supabase.table("lancamentos").delete().eq("projeto_id", nome_real_plano).eq("usuario_id", uid_usuario).gt("data", data_fim_calc).execute()
                
            except Exception as erro_plano:
                print(f"Aviso: Falha ao reconstruir dados serializados do plano: {erro_plano}")

        # 5. ATUALIZA OS DADOS DA LICENÇA NA TABELA PRINCIPAL DE USUÁRIOS
        dados_atualizacao_usuario = {
            "vencimento": nova_data_vencimento_str,
            "data_ult_assinat": hoje.strftime("%Y-%m-%d"),
            "valor_pago": float(valor_esperado)
        }
        
        if tipo_renov_escolhido:
            dados_atualizacao_usuario["tipo_renovacao"] = tipo_renov_escolhido

        supabase.table("usuarios").update(dados_atualizacao_usuario).eq("id", uid_usuario).execute()
        
        # 6. LIMPEZA DOS TEMPORÁRIOS E MEMÓRIA DE SESSÃO
        try:
            supabase.table("pagamentos_temp").delete().eq("pref_id", pref_id_original).execute()
        except: pass
        
        if "alteracao_licenca_pendente" in st.session_state: del st.session_state.alteracao_licenca_pendente
        if "dados_p_salvamento" in st.session_state: del st.session_state.dados_p_salvamento
        
        # 7. RETORNA O MAPA CORRETO PARA LOGIN AUTOMÁTICO IMEDIATO COM O PLANO CARREGADO
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