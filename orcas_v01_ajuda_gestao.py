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
  # st.markdown("### ❓ Central de Ajuda - Gestão")

  # ==============================================================================
  # 1. OPÇÕES DE RADIO BUTTON (NENHUMA SELECIONADA POR PADRÃO + OPÇÃO SAIR)
  # ==============================================================================
  # - index=None garante que inicia desmarcado.
  # - Adicionada a opção "❌ Sair" ao final da lista.
  # ==============================================================================
  opcao = st.radio(
      "Como podemos te ajudar hoje? Selecione um tópico: ################################ Para SAIR, clique novamente no botão AJUDA ",
      [
          "É sua primeira vez aqui?",
          "Você já possui um Plano?",
          "Você quer entender sobre os seus valores?",
          "Visão Geral da Gestão",
    #      "❌ Sair",
      ],
      index=None,
      key="radio_ajuda_gestao",
  )

  st.divider()

  # ==============================================================================
  # 2. ESTRUTURA IF / ELIF PARA CHAMAR O PDF CORRESPONDENTE OU FECHAR
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

  # elif opcao == "❌ Sair":
    # # Interrompe a execução do bloco da ajuda e limpa/fecha o fluxo
    # st.stop()