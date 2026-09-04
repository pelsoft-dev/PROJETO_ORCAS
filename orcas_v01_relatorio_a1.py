import calendar
from datetime import datetime
import io
import re
import pandas as pd
import streamlit as st


def limpar_descricao_parcelada(desc):
  """Remove sufixos numéricos de parcelas (ex: '03 de 10', '1/12', '02 de 05', '03 de 18')

  para permitir a consolidação de todas as parcelas em uma única linha.
  """
  if not isinstance(desc, str):
    return ""
  # Trata "03 de 18", "3 de 18", "03/18", "03DE18", etc.
  desc_limpa = re.sub(
      r"\s*\d{1,2}\s*(?:de|\/)\s*\d{1,2}\s*$",
      "",
      desc,
      flags=re.IGNORECASE,
  )
  return desc_limpa.strip()


def gerar_pdf_monorca_a1(df, projeto_nome, mes_inicial, ano_inicial):
  """Gera o PDF do Relatório MONORCA TIPO A1 ajustado."""
  try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
  except ImportError:
    st.error(
        "A biblioteca 'reportlab' precisa estar instalada no ambiente."
        " Adicione-a ao requirements.txt."
    )
    return None

  buffer = io.BytesIO()

  # Configuração de Página A4 Paisagem
  doc = SimpleDocTemplate(
      buffer,
      pagesize=landscape(A4),
      rightMargin=15,
      leftMargin=15,
      topMargin=15,
      bottomMargin=15,
  )
  elements = []

  # --------------------------------------------------------------------------
  # 1. GERAÇÃO DOS 12 MESES A PARTIR DA DATA INICIAL ESCOLHIDA
  # --------------------------------------------------------------------------
  hoje = datetime.now()
  m_atual_first = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

  data_cursor = datetime(ano_inicial, mes_inicial, 1)

  meses_colunas = []
  for i in range(12):
    m = (data_cursor.month + i - 1) % 12 + 1
    y = data_cursor.year + ((data_cursor.month + i - 1) // 12)
    meses_colunas.append(datetime(y, m, 1))

  nomes_meses_pt = [
      "JAN",
      "FEV",
      "MAR",
      "ABR",
      "MAI",
      "JUN",
      "JUL",
      "AGO",
      "SET",
      "OUT",
      "NOV",
      "DEZ",
  ]

  # --------------------------------------------------------------------------
  # 2. CABEÇALHO DINÂMICO E FORMATADO
  # --------------------------------------------------------------------------
  styles = getSampleStyleSheet()

  # Estilo para quebra de linha dentro da célula do tipo
  header_tipo_style = ParagraphStyle(
      "HeaderTipo",
      parent=styles["Normal"],
      fontName="Helvetica-Bold",
      fontSize=6,
      leading=7,
      alignment=1,  # Centralizado
      textColor=colors.black,
  )

  p_cab_tipo = Paragraph("E=Ent<br/>S=Sai<br/>X=Nulo", header_tipo_style)

  linha_cab_1 = ["", "", ""] + [str(d.year) for d in meses_colunas]

  linha_cab_2 = ["", "", ""]
  for d in meses_colunas:
    if d < m_atual_first:
      linha_cab_2.append("REAL")
    else:
      linha_cab_2.append("PLAN")

  linha_cab_3 = ["DIA", "LANÇAMENTO", p_cab_tipo] + [
      nomes_meses_pt[d.month - 1] for d in meses_colunas
  ]

  # --------------------------------------------------------------------------
  # 3. TRATAMENTO E PREPARAÇÃO DOS DADOS
  # --------------------------------------------------------------------------
  df_work = df.copy() if df is not None and not df.empty else pd.DataFrame()

  if not df_work.empty:
    # Garantir que a ordenação e o agrupamento utilizem a data de vencimento PLANEJADA
    df_work["dt_venc"] = pd.to_datetime(
        df_work["data_vencimento"], errors="coerce"
    )
    df_work["dia"] = df_work["dt_venc"].dt.day.fillna(0).astype(int)
    df_work["ano_mes"] = df_work["dt_venc"].dt.strftime("%Y-%m")

    # Limpar descrição para unir parcelas na mesma linha
    df_work["desc_base"] = df_work["descricao"].apply(
        limpar_descricao_parcelada
    )

    # Identificar Tipo (E, S ou X)
    def verificar_tipo(row):
      parcial_real = float(row.get("parcial_real", 0) or 0)
      cc_tipo = str(row.get("cc_tipo", "") or "").upper()
      cc_qtd_parcelas = float(row.get("cc_qtd_parcelas", 0) or 0)

      if parcial_real == 0 and ("LCL" in cc_tipo) and cc_qtd_parcelas > 0:
        return "X"
      return "E" if str(row.get("tipo", "")).strip() == "Entrada" else "S"

    df_work["tipo_calculado"] = df_work.apply(verificar_tipo, axis=1)

  # --------------------------------------------------------------------------
  # 4. CÁLCULO DOS TOTAIS MENSAIS (DESCONSIDERANDO X)
  # --------------------------------------------------------------------------
  linha_totais = ["", "TOTAL >>>", ""]
  totais_por_mes = []

  for m_dt in meses_colunas:
    chave_m = m_dt.strftime("%Y-%m")
    if not df_work.empty:
      df_m = df_work[df_work["ano_mes"] == chave_m]

      # Desconsidera lançamentos "X"
      df_m_valida = df_m[df_m["tipo_calculado"] != "X"]

      if m_dt < m_atual_first:
        # Mês fechado: Apenas valor_real
        entradas = df_m_valida[df_m_valida["tipo_calculado"] == "E"][
            "valor_real"
        ].sum()
        saidas = df_m_valida[df_m_valida["tipo_calculado"] == "S"][
            "valor_real"
        ].sum()
      else:
        # Mês em aberto: valor_real se > 0 senão valor_plan
        v_calc = df_m_valida.apply(
            lambda r: (
                float(r["valor_real"])
                if float(r.get("valor_real", 0) or 0) > 0
                else float(r.get("valor_plan", 0) or 0)
            ),
            axis=1,
        )
        entradas = v_calc[df_m_valida["tipo_calculado"] == "E"].sum()
        saidas = v_calc[df_m_valida["tipo_calculado"] == "S"].sum()

      saldo = entradas - saidas
    else:
      saldo = 0.0

    totais_por_mes.append(
        f"{saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )

  linha_totais.extend(totais_por_mes)

  # --------------------------------------------------------------------------
  # 5. CONSTRUÇÃO DA GRADE (DIAS 1 A 31)
  # --------------------------------------------------------------------------
  corpo_tabela = [linha_cab_1, linha_cab_2, linha_cab_3, linha_totais]
  linhas_cinzas = []

  for dia in range(1, 32):
    df_dia = (
        df_work[df_work["dia"] == dia]
        if not df_work.empty
        else pd.DataFrame()
    )

    if not df_dia.empty:
      # Agrupa por desc_base e tipo_calculado no dia do vencimento planejado
      agrupamento = (
          df_dia[["desc_base", "tipo_calculado"]].drop_duplicates().values
      )

      for idx_desc, (desc, tipo_es) in enumerate(agrupamento):
        df_item = df_dia[
            (df_dia["desc_base"] == desc)
            & (df_dia["tipo_calculado"] == tipo_es)
        ]

        linha_idx = len(corpo_tabela)
        if tipo_es == "X":
          linhas_cinzas.append(linha_idx)

        linha_item = [str(dia) if idx_desc == 0 else "", desc[:30], tipo_es]

        for m_dt in meses_colunas:
          chave_m = m_dt.strftime("%Y-%m")
          df_m_item = df_item[df_item["ano_mes"] == chave_m]

          if not df_m_item.empty:
            if m_dt < m_atual_first:
              v = df_m_item["valor_real"].sum()
            else:
              v = df_m_item.apply(
                  lambda r: (
                      float(r["valor_real"])
                      if float(r.get("valor_real", 0) or 0) > 0
                      else float(r.get("valor_plan", 0) or 0)
                  ),
                  axis=1,
              ).sum()

            v_str = (
                f"{v:,.2f}"
                .replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
                if v > 0
                else ""
            )
          else:
            v_str = ""

          linha_item.append(v_str)

        corpo_tabela.append(linha_item)
    else:
      linha_vazia = [str(dia), "", ""] + [""] * 12
      corpo_tabela.append(linha_vazia)

  # --------------------------------------------------------------------------
  # 6. ESTILIZAÇÃO E MONTAGEM DO DOCUMENTO
  # --------------------------------------------------------------------------
  col_widths = [20, 180, 35] + [48] * 12

  estilos_base = [
      ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
      ("FONTSIZE", (0, 0), (-1, -1), 6.5),
      ("ALIGN", (0, 0), (-1, -1), "CENTER"),
      ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
      ("ALIGN", (1, 0), (1, -1), "LEFT"),
      ("ALIGN", (3, 3), (-1, -1), "RIGHT"),
      ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D3D3D3")),
      ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
      ("FONTNAME", (0, 0), (-1, 3), "Helvetica-Bold"),
      ("BACKGROUND", (0, 0), (-1, 2), colors.HexColor("#F0F0F0")),
      ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#E6F2FF")),
      ("TEXTCOLOR", (0, 3), (-1, 3), colors.HexColor("#000080")),
      ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
      ("LINEBELOW", (0, 3), (-1, 3), 1.2, colors.black),
  ]

  for l_idx in linhas_cinzas:
    estilos_base.append(
        ("TEXTCOLOR", (3, l_idx), (-1, l_idx), colors.HexColor("#888888"))
    )

  table_style = TableStyle(estilos_base)
  tabela = Table(corpo_tabela, colWidths=col_widths, repeatRows=4)
  tabela.setStyle(table_style)

  title_style = ParagraphStyle(
      "TitleStyle",
      parent=styles["Heading1"],
      fontName="Helvetica-Bold",
      fontSize=12,
      leading=14,
      textColor=colors.HexColor("#003366"),
  )

  dt_atual_str = datetime.now().strftime("%d/%m/%Y")
  elements.append(
      Paragraph(
          f"RELATÓRIO MONORCA TIPO A1 - {projeto_nome.upper()}", title_style
      )
  )
  elements.append(
      Paragraph(
          f"<font size=8 color='#555555'>DATA DE EMISSÃO: {dt_atual_str} |"
          f" PERÍODO: {meses_colunas[0].strftime('%m/%Y')} A"
          f" {meses_colunas[-1].strftime('%m/%Y')}</font>",
          styles["Normal"],
      )
  )
  elements.append(Spacer(1, 8))
  elements.append(tabela)

  doc.build(elements)
  buffer.seek(0)
  return buffer.getvalue()


def exibir_tela_relatorio_a1(supabase, df_lancamentos):
  """Sub-rotina de interface chamada dentro do Admin com seletores de Mês/Ano Inicial."""
  st.markdown("### 📊 Relatório MONORCA TIPO A1")
  st.write(
      "Gere a matriz financeira impresso modelo A1 cobrindo **12 meses"
      " consecutivos** a partir do mês escolhido."
  )

  projeto_atual = st.session_state.get("projeto_ativo", "PADRÃO")
  hoje = datetime.now()

  col_p1, col_p2, col_p3 = st.columns([1.5, 1.5, 2])

  nomes_meses_opcoes = [
      "01 - Janeiro",
      "02 - Fevereiro",
      "03 - Março",
      "04 - Abril",
      "05 - Maio",
      "06 - Junho",
      "07 - Julho",
      "08 - Agosto",
      "09 - Setembro",
      "10 - Outubro",
      "11 - Novembro",
      "12 - Dezembro",
  ]

  with col_p1:
    mes_sel_str = st.selectbox(
        "Mês Inicial", options=nomes_meses_opcoes, index=hoje.month - 1
    )
    mes_inicial = int(mes_sel_str.split(" - ")[0])

  with col_p2:
    anos_disponiveis = [
        hoje.year - 2,
        hoje.year - 1,
        hoje.year,
        hoje.year + 1,
        hoje.year + 2,
    ]
    ano_inicial = st.selectbox(
        "Ano Inicial",
        options=anos_disponiveis,
        index=anos_disponiveis.index(hoje.year),
    )

  with col_p3:
    st.markdown('<div style="margin-top: 25px;"></div>', unsafe_allow_html=True)
    st.info(
        "O relatório cobrirá até"
        f" **{((mes_inicial + 10) % 12) + 1:02d}/{(ano_inicial + ((mes_inicial + 10) // 12))}**."
    )

  st.divider()

  col_btn, col_vazio = st.columns([1, 2])
  with col_btn:
    if st.button(
        "📄 Gerar PDF MONORCA A1", type="primary", use_container_width=True
    ):
      with st.spinner("Compilando dados e gerando PDF..."):
        pdf_bytes = gerar_pdf_monorca_a1(
            df=df_lancamentos,
            projeto_nome=projeto_atual,
            mes_inicial=mes_inicial,
            ano_inicial=ano_inicial,
        )

        if pdf_bytes:
          st.download_button(
              label="⬇️ Baixar PDF A1",
              data=pdf_bytes,
              file_name=(
                  f"RELATORIO_MONORCA_A1_{projeto_atual}_{mes_inicial:02d}_{ano_inicial}.pdf"
              ),
              mime="application/pdf",
              use_container_width=True,
          )
          st.success("Relatório gerado com sucesso!")