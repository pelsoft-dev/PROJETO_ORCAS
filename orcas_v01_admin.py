import streamlit as st
from orcas_v01_dbupdate import renderizar_dbupdate
from orcas_v01_download import render_download
from orcas_v01_upload import render_upload
import orcas_v01_ajuda_admin

def exibir_admin(df, supabase, ID_USUARIO_LOGADO, ir_para_o_topo):
    """
    Hub principal da Tela Admin com layout padronizado de cabeçalho + ajuda,
    e navegação via radio buttons sem seleção inicial.
    """
    projeto_ativo = st.session_state.get("projeto_ativo")

    # --- CABEÇALHO COM TÍTULO E BOTÃO DE AJUDA ---
    col_titulo, col_ajuda = st.columns([0.8, 0.2])
    
    with col_titulo:
        st.title("Admin")
        
    with col_ajuda:
        # Espaçamento para alinhar o botão verticalmente ao título
        st.write("")
        if st.button("AJUDA", type="primary", use_container_width=True):
            orcas_v01_ajuda_admin.exibir_ajuda_admin()

    st.markdown("---")

    # --- SELEÇÃO DE MÓDULO VIA RADIO BUTTONS (SEM SELEÇÃO PADRÃO) ---
    opcao_admin = st.radio(
        "Selecione uma funcionalidade administrativa:",
        options=[
            "✏️ Edição Direta (DB Update)",
            "📥 Download (Exportar)",
            "📤 Upload (Importar)"
        ],
        index=None,
        key="admin_modulo_radio"
    )

    st.markdown("---")

    # --- RENDERIZAÇÃO DO MÓDULO SELECIONADO ---
    if opcao_admin == "✏️ Edição Direta (DB Update)":
        renderizar_dbupdate(df, supabase, ID_USUARIO_LOGADO, ir_para_o_topo)

    elif opcao_admin == "📥 Download (Exportar)":
        render_download(usuario_id=ID_USUARIO_LOGADO, projeto_id=projeto_ativo)

    elif opcao_admin == "📤 Upload (Importar)":
        render_upload(usuario_id=ID_USUARIO_LOGADO, projeto_id=projeto_ativo)

    else:
        st.info("💡 Por favor, escolha uma das opções acima para continuar.")