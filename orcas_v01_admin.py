import streamlit as st
import pandas as pd

def exibir_admin(df, supabase, ir_para_o_topo):
    """
    Sub-rotina da Tela Admin - Edição direta em massa (Layout Excel).
    """
    st.markdown(f'<div class="titulo-tela">Administração: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    # Criamos uma cópia para o editor
    df_admin = df.copy()

    # Adicionamos a coluna de seleção para permitir a exclusão
    df_admin.insert(0, 'Selecionar', False)

    # Conversão de data para string para compatibilidade total com o DataEditor
    if 'data' in df_admin.columns:
        df_admin['data'] = df_admin['data'].astype(str)

    st.warning("⚠️ Cuidado: Alterações aqui impactam diretamente o banco de dados.")

    # Exibe o editor de dados (num_rows dynamic permite flexibilidade, embora o foco seja update)
    df_editado = st.data_editor(
        df_admin, 
        num_rows="dynamic", 
        key="editor_admin_v1",
        use_container_width=True,
        hide_index=True
    )
    
    col_btn_1, col_btn_2 = st.columns(2)

    with col_btn_1:
        if st.button("Salvar Alterações no Banco", use_container_width=True):
            try:
                # Itera pelas linhas para aplicar os updates via ID original
                for i, row in df_editado.iterrows():
                    id_orig = row['id']
                    
                    # Dicionário de atualização conforme estrutura do banco
                    dados_update = {
                        "descricao": row['descricao'],
                        "valor_plan": row['valor_plan'],
                        "valor_real": row['valor_real'],
                        "tipo": row['tipo'],
                        "status": row['status'],
                        "data": str(row['data']) # Retorna como string formatada para o Supabase
                    }
                    
                    # Executa o update no Supabase usando a PK 'id'
                    supabase.table("lancamentos").update(dados_update).eq("id", id_orig).execute()
                
                st.success("Todas as alterações foram salvas com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    with col_btn_2:
        if st.button("Excluir Linhas Selecionadas", use_container_width=True):
            try:
                # Filtra apenas as linhas marcadas para exclusão
                linhas_para_excluir = df_editado[df_editado['Selecionar'] == True]
                
                if not linhas_para_excluir.empty:
                    ids_para_excluir = linhas_para_excluir['id'].tolist()
                    
                    # Executa a exclusão no banco em lote
                    for id_excluir in ids_para_excluir:
                        supabase.table("lancamentos").delete().eq("id", id_excluir).execute()
                    
                    st.success(f"{len(ids_para_excluir)} linha(s) excluída(s) com sucesso!")
                    st.rerun()
                else:
                    st.warning("Nenhuma linha foi selecionada para exclusão.")
            except Exception as e:
                st.error(f"Erro ao excluir: {e}")

    st.divider()
    
    # Ferramentas de manutenção do sistema
    col_adm1, col_adm2 = st.columns(2)
    
    with col_adm1:
        if st.button("Limpar Cache do Sistema", use_container_width=True):
            st.cache_data.clear()
            st.success("Cache limpo!")
            st.rerun()

    with col_adm2:
        if st.button("Voltar ao Topo", key="btn_topo_admin", use_container_width=True): 
            ir_para_o_topo()