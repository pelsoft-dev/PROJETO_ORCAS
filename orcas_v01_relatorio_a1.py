import calendar
from datetime import datetime
import io
import re
import pandas as pd
import streamlit as st


def limpar_descricao_parcelada(desc):
  """Remove sufixos de parcelas (ex: '03 de 10', '1/12', '02 de 05', '03 de 18') e espaços extras para garantir a consolidação em uma única linha."""
  if not isinstance(desc, str):
    return ""

  # Remove padrões do tipo: "01 de 02", "1/12", "01/10", " 03 DE 18" no final ou meio da frase
  desc_limpa = re.sub(
      r"\s*\b\d{1,2}\s*(?:de|\/)\s*\d{1,2}\b", "", desc, flags=re.IGNORECASE
  )
  # Remove múltiplos espaços mantendo texto limpo
  return re.sub(r"\s+", " ", desc_limpa).strip().upper()


def obter_valor_real_calculado(row):
  """Retorna o valor realizado correto, priorizando a soma de parciais caso existam."""
  v_real = float(row.get("valor_real", 0) or 0)
  p_real = float(row.get("parcial_real", 0) or 0)
  return max(v_real, p_real)


def gerar_pdf_monorca_a1(df, projeto_nome, mes_inicial, ano_inicial):
  """Gera o PDF do Relatório MONORCA TIPO A1 consolidando parcelas e parciais."""
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
    st.error("A biblioteca 'reportlab' precisa estar instalada no ambiente.")
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
  # 1. PERÍODO DE 12 MESES
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
  # 2. CABEÇALHO DADOS
  # --------------------------------------------------------------------------
  styles = getSampleStyleSheet()

  header_tipo_style = ParagraphStyle(
      "HeaderTipo",
      parent=styles["Normal"],
      fontName="Helvetica-Bold",
      fontSize=6,
      leading=7,
      alignment=1,
      textColor=colors.black,
  )

  p_cab_tipo = Paragraph("E=Ent<br/>S=Sai<br/>X=Nulo", header_tipo_style)

  linha_cab_1 = ["", "", ""] + [str(d.year) for d in meses_colunas]
  linha_cab_2 = ["", "", ""] + [
      "REAL" if d < m_atual_first else "PLAN" for d in meses_colunas
  ]
  linha_cab_3 = ["DIA", "LANÇAMENTO", p_cab_tipo] + [
      nomes_meses_pt[d.month - 1] for d in meses_colunas
  ]

  # --------------------------------------------------------------------------
  # 3. PRÉ-PROCESSAMENTO DOS DADOS
  # --------------------------------------------------------------------------
  df_work = df.copy() if df is not None and not df.empty else pd.DataFrame()

  if not df_work.empty:
    df_work["dt_venc"] = pd.to_datetime(
        df_work["data_vencimento"], errors="coerce"
    )
    df_work["dia"] = df_work["dt_venc"].dt.day.fillna(1).astype(int)
    df_work["ano_mes"] = df_work["dt_venc"].dt.strftime("%Y-%m")

    # Limpeza de descrição para agrupar em 1 única linha
    df_work["desc_base"] = df_work["descricao"].apply(
        limpar_descricao_parcelada
    )

    # Cálculo correto de Valor Real (suporta parciais)
    df_work["valor_real_calc"] = df_work.apply(
        obter_valor_real_calculado, axis=1
    )

    def verificar_tipo(row):
      parcial_real = float(row.get("parcial_real", 0) or 0)
      cc_tipo = str(row.get("cc_tipo", "") or "").upper()
      cc_qtd_parcelas = float(row.get("cc_qtd_parcelas", 0) or 0)

      if parcial_real == 0 and ("LCL" in cc_tipo) and cc_qtd_parcelas > 0:
        return "X"
      return "E" if str(row.get("tipo", "")).strip() == "Entrada" else "S"

    df_work["tipo_calculado"] = df_work.apply(verificar_tipo, axis=1)

  # --------------------------------------------------------------------------
  # 4. TOTAIS MENSAIS
  # --------------------------------------------------------------------------
  linha_totais = ["", "TOTAL >>>", ""]
  totais_por_mes = []

  for m_dt in meses_colunas:
    chave_m = m_dt.strftime("%Y-%m")
    if not df_work.empty:
      df_m = df_work[df_work["ano_mes"] == chave_m]
      df_m_valida = df_m[df_m["tipo_calculado"] != "X"]

      if m_dt < m_atual_first:
        entradas = df_m_valida[df_m_valida["tipo_calculado"] == "E"][
            "valor_real_calc"
        ].sum()
        saidas = df_m_valida[df_m_valida["tipo_calculado"] == "S"][
            "valor_real_calc"
        ].sum()
      else:
        v_calc = df_m_valida.apply(
            lambda r: (
                r["valor_real_calc"]
                if r["valor_real_calc"] > 0
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
  # 5. MONTAGEM DA GRADE CONSOLIDADA (1 LINHA POR LANÇAMENTO LIMPO)
  # --------------------------------------------------------------------------
  corpo_tabela = [linha_cab_1, linha_cab_2, linha_cab_3, linha_totais]
  linhas_cinzas = []

  if not df_work.empty:
    # Agrupa por Descrição Limpa + Tipo
    grupos = df_work.groupby(["desc_base", "tipo_calculado"])

    # Estrutura para ordenar as linhas pelo menor dia de vencimento encontrado
    linhas_processadas = []

    for (desc, tipo_es), df_grupo in grupos:
      dia_exibicao = int(df_grupo["dia"].min())  # Menor dia encontrado

      linha_item = [str(dia_exibicao), desc[:30], tipo_es]

      for m_dt in meses_colunas:
        chave_m = m_dt.strftime("%Y-%m")
        df_m_item = df_grupo[df_grupo["ano_mes"] == chave_m]

        if not df_m_item.empty:
          if m_dt < m_atual_first:
            v = df_m_item["valor_real_calc"].sum()
          else:
            v = df_m_item.apply(
                lambda r: (
                    r["valor_real_calc"]
                    if r["valor_real_calc"] > 0
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

      linhas_processadas.append((dia_exibicao, desc, tipo_es, linha_item))

    # Ordenar linhas pelo dia e depois por descrição
    linhas_processadas.sort(key=lambda x: (x[0], x[1]))

    dia_anterior = None
    for dia_exib, desc, tipo_es, linha_item in linhas_processadas:
      # Oculta repetidos do número do dia se for a mesma sequência
      if dia_exib == dia_anterior:
        linha_item[0] = ""
      else:
        dia_anterior = dia_exib

      if tipo_es == "X":
        linhas_cinzas.append(len(corpo_tabela))

      corpo_tabela.append(linha_item)

  # --------------------------------------------------------------------------
  # 6. ESTILIZAÇÃO E DOCUMENTO
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
  """Interface no Streamlit."""
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