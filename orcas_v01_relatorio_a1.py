import calendar
from datetime import datetime
import io
import pandas as pd
import streamlit as st

# ReportLab imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def gerar_pdf_monorca_a1(df, projeto_nome, mes_inicial, ano_inicial):
    """
    Gera o PDF do Relatório MONORCA TIPO A1.
    - Orientação: A4 Landscape
    - Matriz de exatamente 12 meses a partir de (mes_inicial/ano_inicial)
    - Agrupado por Dia do Mês (1 a 31)
    """
    buffer = io.BytesIO()
    
    # Configuração de Página A4 Paisagem
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=15,
        leftMargin=15,
        topMargin=15,
        bottomMargin=15
    )
    elements = []
    
    # --------------------------------------------------------------------------
    # 1. GERAÇÃO DOS 12 MESES A PARTIR DA DATA INICIAL ESCOLHIDA
    # --------------------------------------------------------------------------
    hoje = datetime.now()
    data_cursor = datetime(ano_inicial, mes_inicial, 1)
    
    meses_colunas = []
    for i in range(12):
        m = (data_cursor.month + i - 1) % 12 + 1
        y = data_cursor.year + ((data_cursor.month + i - 1) // 12)
        meses_colunas.append(datetime(y, m, 1))

    nomes_meses_pt = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
    
    # --------------------------------------------------------------------------
    # 2. CABEÇALHO DINÂMICO (ANOS, REAL x PLAN E NOMES DOS MESES)
    # --------------------------------------------------------------------------
    # Linha 1: Anos
    linha_cab_1 = ["", ""] + [str(d.year) for d in meses_colunas]
        
    # Linha 2: Marcação REAL x PLAN comparando com o mês/ano corrente
    linha_cab_2 = ["", ""]
    m_atual_first = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    for d in meses_colunas:
        if d < m_atual_first:
            linha_cab_2.append("<< REAL")
        else:
            linha_cab_2.append("PLAN >>")

    # Linha 3: Nomes dos Meses
    linha_cab_3 = ["DIA", "LANÇAMENTO", "$E/S$"] + [nomes_meses_pt[d.month - 1] for d in meses_colunas]
    
    # --------------------------------------------------------------------------
    # 3. TRATAMENTO DOS DADOS E LINHA DE TOTAL (SALDO)
    # --------------------------------------------------------------------------
    df_work = df.copy() if df is not None and not df.empty else pd.DataFrame()
    
    if not df_work.empty:
        df_work['dt_venc'] = pd.to_datetime(df_work['data_vencimento'], errors='coerce')
        df_work['dia'] = df_work['dt_venc'].dt.day.fillna(0).astype(int)
        df_work['ano_mes'] = df_work['dt_venc'].dt.strftime('%Y-%m')
        df_work['valor_final'] = df_work.apply(
            lambda r: float(r['valor_real']) if float(r.get('valor_real', 0)) > 0 else float(r.get('valor_plan', 0)),
            axis=1
        )
    
    linha_totais = ["", "TOTAL >>>", ""]
    totais_por_mes = []
    
    for m_dt in meses_colunas:
        chave_m = m_dt.strftime('%Y-%m')
        if not df_work.empty:
            df_m = df_work[df_work['ano_mes'] == chave_m]
            entradas = df_m[df_m['tipo'] == 'Entrada']['valor_final'].sum()
            saidas = df_m[df_m['tipo'] == 'Saída']['valor_final'].sum()
            saldo = entradas - saidas
        else:
            saldo = 0.0
            
        totais_por_mes.append(f"{saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        
    linha_totais.extend(totais_por_mes)

    # --------------------------------------------------------------------------
    # 4. CONSTRUÇÃO DA GRADE (DIAS 1 A 31)
    # --------------------------------------------------------------------------
    corpo_tabela = [linha_cab_1, linha_cab_2, linha_cab_3, linha_totais]
    
    for dia in range(1, 32):
        df_dia = df_work[df_work['dia'] == dia] if not df_work.empty else pd.DataFrame()
        
        if not df_dia.empty:
            descricoes = df_dia['descricao'].unique()
            for idx_desc, desc in enumerate(descricoes):
                df_item = df_dia[df_dia['descricao'] == desc]
                tipo_es = "E" if df_item.iloc[0]['tipo'] == "Entrada" else "S"
                
                cc_tipo = str(df_item.iloc[0].get('cc_tipo', ''))
                if "LCL" in cc_tipo or "CCP" in cc_tipo:
                    if dia == 0 or pd.isnull(df_item.iloc[0]['dt_venc']):
                        tipo_es = "X"

                linha_item = [str(dia) if idx_desc == 0 else "", desc[:30], tipo_es]
                
                for m_dt in meses_colunas:
                    chave_m = m_dt.strftime('%Y-%m')
                    df_m_item = df_item[df_item['ano_mes'] == chave_m]
                    if not df_m_item.empty:
                        v = df_m_item['valor_final'].sum()
                        v_str = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if v > 0 else ""
                    else:
                        v_str = ""
                    linha_item.append(v_str)
                
                corpo_tabela.append(linha_item)
        else:
            linha_vazia = [str(dia), "", ""] + [""] * 12
            corpo_tabela.append(linha_vazia)

    # --------------------------------------------------------------------------
    # 5. ESTILIZAÇÃO E MONTAGEM DO DOCUMENTO
    # --------------------------------------------------------------------------
    col_widths = [25, 180, 35] + [48] * 12

    table_style = TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('ALIGN', (3, 3), (-1, -1), 'RIGHT'),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#D3D3D3')),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.black),
        ('FONTNAME', (0, 0), (-1, 3), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 2), colors.HexColor('#F0F0F0')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#E6F2FF')),
        ('TEXTCOLOR', (0, 3), (-1, 3), colors.HexColor('#000080')),
        ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('LINEBELOW', (0, 3), (-1, 3), 1.2, colors.black),
    ])

    tabela = Table(corpo_tabela, colWidths=col_widths, repeatRows=4)
    tabela.setStyle(table_style)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=14,
        textColor=colors.HexColor('#003366')
    )
    
    dt_atual_str = datetime.now().strftime('%d/%m/%Y')
    elements.append(Paragraph(f"RELATÓRIO MONORCA TIPO A1 - {projeto_nome.upper()}", title_style))
    elements.append(Paragraph(f"<font size=8 color='#555555'>DATA DE EMISSÃO: {dt_atual_str} | PERÍODO: {meses_colunas[0].strftime('%m/%Y')} A {meses_colunas[-1].strftime('%m/%Y')}</font>", styles['Normal']))
    elements.append(Spacer(1, 8))
    elements.append(tabela)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def exibir_tela_relatorio_a1(supabase, df_lancamentos):
    """
    Sub-rotina de interface chamada dentro do Admin com seletores de Mês/Ano Inicial.
    """
    st.markdown("### 📊 Relatório MONORCA TIPO A1")
    st.write("Gere a matriz financeira impresso modelo A1 cobrindo **12 meses consecutivos** a partir do mês escolhido.")
    
    projeto_atual = st.session_state.get("projeto_ativo", "PADRÃO")
    
    # --------------------------------------------------------------------------
    # SELEÇÃO DO MÊS E ANO INICIAL
    # --------------------------------------------------------------------------
    hoje = datetime.now()
    
    col_p1, col_p2, col_p3 = st.columns([1.5, 1.5, 2])
    
    nomes_meses_opcoes = [
        "01 - Janeiro", "02 - Fevereiro", "03 - Março", "04 - Abril",
        "05 - Maio", "06 - Junho", "07 - Julho", "08 - Agosto",
        "09 - Setembro", "10 - Outubro", "11 - Novembro", "12 - Dezembro"
    ]
    
    with col_p1:
        mes_sel_str = st.selectbox(
            "Mês Inicial",
            options=nomes_meses_opcoes,
            index=hoje.month - 1
        )
        mes_inicial = int(mes_sel_str.split(" - ")[0])

    with col_p2:
        anos_disponiveis = [hoje.year - 2, hoje.year - 1, hoje.year, hoje.year + 1, hoje.year + 2]
        ano_inicial = st.selectbox(
            "Ano Inicial",
            options=anos_disponiveis,
            index=anos_disponiveis.index(hoje.year)
        )

    with col_p3:
        st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
        st.info(f"O relatório cobrirá até **{((mes_inicial + 10) % 12) + 1:02d}/{(ano_inicial + ((mes_inicial + 10) // 12))}**.")

    st.divider()

    # BOTÃO PARA GERAR PDF
    col_btn, col_vazio = st.columns([1, 2])
    with col_btn:
        if st.button("📄 Gerar PDF MONORCA A1", type="primary", use_container_width=True):
            with st.spinner("Compilando dados e gerando PDF..."):
                pdf_bytes = gerar_pdf_monorca_a1(
                    df=df_lancamentos,
                    projeto_nome=projeto_atual,
                    mes_inicial=mes_inicial,
                    ano_inicial=ano_inicial
                )
                
                st.download_button(
                    label="⬇️ Baixar PDF A1",
                    data=pdf_bytes,
                    file_name=f"RELATORIO_MONORCA_A1_{projeto_atual}_{mes_inicial:02d}_{ano_inicial}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                st.success("Relatório gerado com sucesso!")