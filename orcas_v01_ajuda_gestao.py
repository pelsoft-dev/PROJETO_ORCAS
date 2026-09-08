import io
import os
import pypdfium2 as pdfium
import streamlit as st


def renderizar_ajuda_gestao():
    """Renderiza todas as páginas do PDF como imagens sempre atualizadas."""
    caminho_pdf = "orcas-ajuda-gestao.pdf"

    if os.path.exists(caminho_pdf):
        # Lê os bytes brutos diretamente do disco para evitar cache do sistema
        with open(caminho_pdf, "rb") as f:
            pdf_bytes = f.read()

        # Carrega o PDF a partir do fluxo de memória atualizado
        pdf = pdfium.PdfDocument(io.BytesIO(pdf_bytes))

        # Container para exibição
        with st.container():
            for i, page in enumerate(pdf):
                image = page.render(scale=2).to_pil()
                st.image(
                    image,
                    use_container_width=True,
                    caption=f"Página {i + 1} de {len(pdf)}",
                )
    else:
        st.error(f"Arquivo PDF não encontrado: `{caminho_pdf}`")