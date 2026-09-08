import os
import pypdfium2 as pdfium
import streamlit as st


def renderizar_ajuda_gestao():
    """Renderiza todas as páginas do PDF como imagens dentro do aplicativo."""
    caminho_pdf = "orcas-ajuda-pdf.pdf"

    if os.path.exists(caminho_pdf):
        # Abre o PDF e renderiza página por página
        pdf = pdfium.PdfDocument(caminho_pdf)

        # Container com fundo azul para manter o estilo visual
        with st.container():
            for i, page in enumerate(pdf):
                # Renderiza a página em imagem de alta resolução (scale=2)
                image = page.render(scale=2).to_pil()
                st.image(
                    image,
                    use_container_width=True,
                    caption=f"Página {i + 1} de {len(pdf)}",
                )
    else:
        st.error(f"Arquivo PDF não encontrado: `{caminho_pdf}`")