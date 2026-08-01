import streamlit as st
from orcas_v01_dbupdate import renderizar_dbupdate
from orcas_v01_download import render_download
from orcas_v01_upload import render_upload

def exibir_admin(df, supabase, ID_USUARIO_LOGADO, ir_para_o_topo):
    """
    Hub principal da Tela Admin.
    Organiza as sub-rotinas administrativas em abas.
    """
    st.markdown(f'<div class="titulo-tela" style="margin-top:0px;">⚙️ Painel do Administrador</div>', unsafe_allow_html=True)

    # Criação das abas administrativas
    tab_dbupdate, tab_download, tab_upload = st.tabs([
        "✏️ Edição Direta (DB Update)", 
        "📥 Download (Exportar)", 
        "📤 Upload (Importar)"
    ])

    # Aba 1: Funcionalidade histórica do Admin
    with tab_dbupdate:
        renderizar_dbupdate(df, supabase, ID_USUARIO_LOGADO, ir_para_o_topo)

    # Aba 2: Exportação em Excel
    with tab_download:
        render_download()

    # Aba 3: Importação via Excel
    with tab_upload:
        render_upload()