import base64
import os
import streamlit as st


def renderizar_ajuda_gestao():
    """Renderiza o PDF de ajuda da tela de Gestão dentro de um container com rolagem."""
    caminho_pdf = "orcas-ajuda-pdf.pdf"

    if os.path.exists(caminho_pdf):
        with open(caminho_pdf, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode("utf-8")

        # Utiliza o leitor da Mozilla via CDN para renderizar Data URI
        pdf_display = f"""
            <div style="background-color: #007ba7; padding: 10px; border-radius: 8px; margin-bottom: 20px;">
                <iframe 
                    src="https://mozilla.github.io/pdf.js/web/viewer.html?file=data:application/pdf;base64,{base64_pdf}" 
                    width="100%" 
                    height="600px" 
                    style="border: none; border-radius: 5px;">
                </iframe>
            </div>
        """
        st.markdown(pdf_display, unsafe_allow_html=True)
    else:
        st.error(f"Arquivo PDF não encontrado: `{caminho_pdf}`")