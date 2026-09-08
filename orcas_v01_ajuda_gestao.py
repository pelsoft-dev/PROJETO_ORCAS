import base64
import os
import streamlit as st


def renderizar_ajuda_gestao():
    """Renderiza o PDF de ajuda da tela de Gestão dentro de um container com rolagem."""
    caminho_pdf = "orcas-ajuda-pdf.pdf"

    if os.path.exists(caminho_pdf):
        with open(caminho_pdf, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode("utf-8")

        # Embutimento nativo HTML5 compatível com Streamlit Cloud
        pdf_display = f"""
            <div style="background-color: #007ba7; padding: 10px; border-radius: 8px; margin-bottom: 20px;">
                <embed 
                    src="data:application/pdf;base64,{base64_pdf}" 
                    width="100%" 
                    height="600px" 
                    type="application/pdf">
                </embed>
            </div>
        """
        st.markdown(pdf_display, unsafe_allow_html=True)
    else:
        st.error(f"Arquivo PDF não encontrado: `{caminho_pdf}`")