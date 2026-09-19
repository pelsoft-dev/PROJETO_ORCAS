import io
import os
import pypdfium2 as pdfium
import streamlit as st


def exibir_pdf(caminho_pdf):
  """Função auxiliar para abrir e exibir as páginas do PDF escolhido."""
  if os.path.exists(caminho_pdf):
    with open(caminho_pdf, "rb") as f:
      pdf_bytes = f.read()

    pdf = pdfium.PdfDocument(io.BytesIO(pdf_bytes))

    with st.container():
      for i, page in enumerate(pdf):
        image = page.render(scale=2).to_pil()
        st.image(
            image,
            use_container_width=True,
            caption=f"Página {i + 1} de {len(pdf)}",
        )
  else:
    st.error(f"⚠️ Arquivo PDF não encontrado: `{caminho_pdf}`")


def renderizar_ajuda_gestao():
  """Renderiza as opções de ajuda e carrega o PDF correspondente."""

  # ==============================================================================
  # 1. CABEÇALHO CUSTOMIZADO COM TEXTO ALINHADO À ESQUERDA E À DIREITA
  # ==============================================================================
  st.markdown(
      """
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-weight: 600; font-size: 0.95rem;">Como podemos te ajudar?</span>
          <span style="font-size: 0.95rem; color: #6c757d; font-weight: 500;">💡Para SAIR, clique no AJUDA novamente</span>
      </div>
      """,
      unsafe_allow_html=True,
  )

  # ==============================================================================
  # 2. OPÇÕES DE RADIO BUTTON (LABEL OCULTA PARA USAR O CABEÇALHO ACIMA)
  # ==============================================================================
  opcao = st.radio(
      "Como podemos te ajudar hoje?",
      [
          "É sua primeira vez aqui?",
          "Você já possui um Plano?",
          "Você quer entender sobre os seus valores?",
          "Visão Geral da Gestão",
      ],
      index=None,
      key="radio_ajuda_gestao",
      label_visibility="collapsed",  # Oculta a label padrão para evitar duplicação
  )

  st.divider()

  # ==============================================================================
  # 3. ESTRUTURA IF / ELIF PARA CHAMAR O PDF CORRESPONDENTE
  # ==============================================================================
  if opcao is None:
    # Nenhuma opção selecionada ainda
    st.info("👆 Selecione uma das opções acima para visualizar a ajuda.")

  elif opcao == "É sua primeira vez aqui?":
    exibir_pdf("orcas-ajuda-gestao.pdf")

  elif opcao == "Você já possui um Plano?":
    exibir_pdf("orcas-ajuda-ja-possui-plano.pdf")

  elif opcao == "Você quer entender sobre os seus valores?":
    exibir_pdf("orcas-ajuda-valores.pdf")

  elif opcao == "Visão Geral da Gestão":
    exibir_pdf("orcas-ajuda-gestao.pdf")