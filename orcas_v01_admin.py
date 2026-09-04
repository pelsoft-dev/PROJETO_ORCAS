import streamlit as st
import pandas as pd
from orcas_v01_dbupdate import renderizar_dbupdate
from orcas_v01_download import render_download
from orcas_v01_upload import render_upload
from orcas_v01_ajuda_admin import renderizar_ajuda_admin
from orcas_v01_relatorio_a1 import exibir_tela_relatorio_a1

def exibir_admin(df, supabase, ID_USUARIO_LOGADO, ir_para_o_topo):
    """
    Hub principal da Tela Admin com cabeçalho padrão
    e navegação via radio buttons sem seleção inicial.
    """
    projeto_ativo = st.session_state.get("projeto_ativo", "")

    # --- CABEÇALHO ALINHADO COM BOTÃO DE AJUDA ---
    col_titulo, col_ajuda = st.columns([4, 1])
    
    with col_titulo:
        st.markdown(
            f'<div class="titulo-tela" style="margin-top:0px;">Administração: {projeto_ativo}</div>', 
            unsafe_allow_html=True
        )
        
    with col_ajuda:
        st.markdown("""
            <style>
            div.stButton > button:first-child {
                background-color: #007ba7 !important;
                color: white !important;
                border: none !important;
            }
            div.stButton > button:first-child:hover {
                background-color: #005f81 !important;
                color: white !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        if st.button("AJUDA", type="primary", use_container_width=True, key="btn_ajuda_admin_main"):
            st.session_state["exibir_ajuda_admin"] = not st.session_state.get("exibir_ajuda_admin", False)
            st.rerun()

    # --- EXIBIÇÃO DA TELA DE AJUDA SE O BOTÃO FOR CLICADO ---
    if st.session_state.get("exibir_ajuda_admin", False):
        renderizar_ajuda_admin()

    st.markdown("---")

    # --- SELEÇÃO DE MÓDULO VIA RADIO BUTTONS (SEM SELEÇÃO PADRÃO) ---
    opcao_admin = st.radio(
        "Selecione uma funcionalidade administrativa:",
        options=[
            "✏️ Edição Direta (DB Update)",
            "📥 Download (Exportar)",
            "📤 Upload (Importar)",
            "📊 Gerar relatório A1 - Lançamentos em 12 meses"
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

    elif opcao_admin == "📊 Gerar relatório A1 - Lançamentos em 12 meses":
        exibir_tela_relatorio_a1(supabase, df)

    else:
        st.info("💡 Por favor, escolha uma das opções acima para continuar.")