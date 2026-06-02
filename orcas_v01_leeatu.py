import streamlit as st
from supabase import create_client, Client

# 1. CONFIGURAÇÃO DE CONEXÃO ISOLADA
# Como você quer rodar este arquivo de forma independente via "streamlit run", 
# ele precisa saber como se conectar ao seu banco de dados.
URL_DO_SUPABASE = "https://oqmeyhkyxuprubwqcwuj.supabase.co"
CHAVE_ANON_SUPABASE = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9xbWV5aGt5eHVwcnVid3Fjd3VqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM4NjU3ODMsImV4cCI6MjA4OTQ0MTc4M30.ALFqZ0DjhJNQ2mxkS9mZvaN_8dyBuqlEB74omH2iI7U"

# Inicializa o cliente do Supabase de forma standalone
if "supabase_isolado" not in st.session_state:
    st.session_state.supabase_isolado = create_client(URL_DO_SUPABASE, CHAVE_ANON_SUPABASE)

supabase = st.session_state.supabase_isolado

# 2. FUNÇÃO PRINCIPAL DE LEITURA E ATUALIZAÇÃO
def executar_leitura_e_atualizacao():
    st.title("🔄 Execução Isolada de Atualização")
    
    planoaserlido = "PLANO PSP OFICIAL"
    st.write(f"🔍 Buscando o plano '{planoaserlido}' na tabela `pagamentos_temp`...")
    
    try:
        # Lê o registro temporário para extrair as variáveis individuais
        res_temp = supabase.table("pagamentos_temp")\
            .select("usuario_id, projeto_id, tipo_renovacao, data_ini, data_fim, zap_ativo, email_ativo")\
            .eq("projeto_id", planoaserlido)\
            .limit(1)\
            .execute()
            
        if not res_temp.data:
            st.warning(f"⚠️ Nenhum registro encontrado para o plano: {planoaserlido}")
            return
            
        dados_frescos = res_temp.data[0]
        uid_usuario = dados_frescos.get("usuario_id")
        v_projeto_id = dados_frescos.get("projeto_id")
        v_tipo_renovacao = dados_frescos.get("tipo_renovacao")
        
        # Variáveis locais recebendo os campos nulos ou preenchidos diretamente
        v_data_ini = dados_frescos.get("data_ini")
        v_data_fim = dados_frescos.get("data_fim")
        v_zap_ativo = dados_frescos.get("zap_ativo")
        v_email_ativo = dados_frescos.get("email_ativo")
        
        st.info(f"📋 Registro encontrado! Aplicando dados para o Usuário: {uid_usuario}")

        # ==============================================================================
        # ATUALIZAÇÃO DA TABELA config_projetos (DIRETA E EXPLICÍTICA, SEM PAYLOADS)
        # ==============================================================================
        st.write("🚀 Atualizando a tabela `config_projetos`...")
        
        # Executa o update com o dicionário de campos montado diretamente dentro do método
        supabase.table("config_projetos").update({
            "data_ini": v_data_ini,
            "data_fim": v_data_fim,
            "zap_ativo": v_zap_ativo,
            "email_ativo": v_email_ativo
        }).eq("projeto_id", v_projeto_id).eq("usuario_id", uid_usuario).execute()
        
        st.success("✅ Tabela `config_projetos` atualizada com sucesso!")

        # ==============================================================================
        # ATUALIZAÇÃO DA TABELA usuarios (CAMPO tipo_renovacao)
        # ==============================================================================
        if uid_usuario and v_tipo_renovacao:
            st.write("🚀 Atualizando o campo `tipo_renovacao` na tabela `usuarios`...")
            
            supabase.table("usuarios").update({
                "tipo_renovacao": v_tipo_renovacao
            }).eq("id", uid_usuario).execute()
            
            st.success("✅ Campo `tipo_renovacao` atualizado com sucesso na tabela `usuarios`!")
            
    except Exception as e:
        st.error(f"🚨 Ocorreu um erro durante a execução: {e}")

# 3. GATILHO DE EXECUÇÃO AUTOMÁTICA DO STREAMLIT
# Quando você rodar "streamlit run orcas_v01_leeatu.py", esta linha chama a função acima imediatamente.
if __name__ == "__main__":
    executar_leitura_e_atualizacao()