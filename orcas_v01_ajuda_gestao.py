import os
import streamlit as st


def renderizar_ajuda_gestao():
    """Oferece o PDF de ajuda para visualização/download nativo."""
    caminho_pdf = "orcas-ajuda-pdf.pdf"

    if os.path.exists(caminho_pdf):
        with open(caminho_pdf, "rb") as f:
            pdf_bytes = f.read()

        st.download_button(
            label="📄 Baixar / Abrir PDF de Ajuda",
            data=pdf_bytes,
            file_name="orcas-ajuda-gestao.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
    else:
        st.error(f"Arquivo PDF não encontrado: `{caminho_pdf}`")