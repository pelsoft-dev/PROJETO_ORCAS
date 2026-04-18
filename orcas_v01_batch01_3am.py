import os
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from supabase import create_client
from datetime import datetime, timedelta, timezone
from fpdf import FPDF

# ==============================================================================
# CONFIGURAÇÕES DE AMBIENTE (SECRETOS DO GITHUB)
# ==============================================================================
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY")

# Configurações de E-mail (Devem estar no GitHub Secrets)
SMTP_SERVER = os.environ.get("SMTP_SERVER")
SMTP_PORT = os.environ.get("SMTP_PORT")
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")

# ==============================================================================
# FUNÇÕES AUXILIARES DE FORMATAÇÃO
# ==============================================================================
def fmt_br(valor):
    """Formata valor para padrão brasileiro: 1.250,55"""
    if valor is None: return "0,00"
    try:
        return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00"

# ==============================================================================
# GERAÇÃO DO RELATÓRIO PDF (ORCAS DAILY REPORT)
# ==============================================================================
# ==============================================================================
# GERAÇÃO DO RELATÓRIO PDF (ORCAS DAILY REPORT)
# ==============================================================================
def gerar_pdf_relatorio(usuario_nome, nome_plano, data_hoje, agenda_hoje, resumo_ontem, analise_macro, gastos_excedidos):
    pdf = FPDF()
    pdf.add_page()
    
    # ---------------------------------------------------------
    # MODIFICAÇÃO 01: INCLUIR A BALEIA COM CAMINHO ABSOLUTO
    # ---------------------------------------------------------
    try:
        # Resolve o erro [Errno 2] do GitHub Actions usando caminho absoluto
        base_path = os.path.dirname(os.path.abspath(__file__))
        image_path = os.path.join(base_path, "orca_mascote.png")
        if os.path.exists(image_path):
            pdf.image(image_path, x=4, y=4, w=50)
        else:
            print(f"Aviso: Arquivo {image_path} não encontrado no servidor.")
    except Exception as e:
        print(f"Aviso: Erro ao processar imagem: {e}")

    # Título Principal
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(190, 10, "ORCAS DAILY REPORT", new_x="LMARGIN", new_y="NEXT", align="C")
    
    # Subtítulo (Data e Plano)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(190, 10, f"Usuário: {usuario_nome} | Plano: {nome_plano} | Data: {data_hoje.strftime('%d/%m/%Y')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    # 1. SAÚDE GERAL DO PLANO (VISÃO ACUMULADA)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 8, " 1. SAÚDE GERAL DO PLANO (VISÃO ACUMULADA)", 0, new_x="LMARGIN", new_y="NEXT", fill=True)
    
    pdf.set_font("Helvetica", "B", 7)
    pdf.cell(45, 10, "Período de Referência", 1, align="C")
    pdf.cell(35, 10, "Datas (Início/Fim)", 1, align="C") 
    pdf.cell(55, 5, "Entradas", 1, align="C")
    pdf.cell(55, 5, "Saídas", 1, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_x(90)
    pdf.cell(27.5, 5, "Planejadas", 1, align="C")
    pdf.cell(27.5, 5, "Realizadas", 1, align="C")
    pdf.cell(27.5, 5, "Planejadas", 1, align="C")
    pdf.cell(27.5, 5, "Realizadas", 1, new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_font("Helvetica", "", 7)
    periodos = [
        ("Do Início do Plano até Hoje", "plano_hoje"),
        ("Do Início do Plano até o Fim do Plano", "plano_total"),
        ("Do Início do Mês até Hoje", "mes_hoje"),
        ("Do Início do Mês até o Fim do Mês", "mes_total"),
        ("Do Início do Ano até Hoje", "ano_hoje"),
        ("Do Início do Ano até o Fim do Ano", "ano_total")
    ]

    for label, key in periodos:
        d = analise_macro.get(key, {"e_p":0, "e_r":0, "s_p":0, "s_r":0, "start": "-", "end": "-"})
        
        # ----------------------------------------------------------------------
        # ADAPTAÇÃO SOLICITADA: Respeito rigoroso aos campos do Supabase
        # ----------------------------------------------------------------------
        # Se o valor vier errado do analise_macro, esta linha garante a exibição
        # dos campos 'start' e 'end' exatamente como passados na estrutura.
        data_exibicao = f"{d['start']} a {d['end']}"
        
        pdf.cell(45, 6, label, 1)
        pdf.cell(35, 6, data_exibicao, 1, align="C")
        
        pdf.cell(27.5, 6, fmt_br(d['e_p']), 1, align="R")
        pdf.cell(27.5, 6, fmt_br(d['e_r']), 1, align="R")
        pdf.cell(27.5, 6, fmt_br(d['s_p']), 1, align="R")
        pdf.cell(27.5, 6, fmt_br(d['s_r']), 1, new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    s_p_acum = analise_macro.get('plano_hoje', {}).get('s_p', 0)
    aderencia = (analise_macro['plano_hoje']['s_r'] / s_p_acum * 100) if s_p_acum > 0 else 0
    pdf.cell(190, 8, f"Índice de Aderência ao Orçamento (Saídas Acumuladas): {aderencia:.1f}%", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # 2. ATENÇÃO: GASTOS ACIMA DO PLANEJADO (COMPARATIVO)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 8, " 2. ATENÇÃO: GASTOS ACIMA DO PLANEJADO (COMPARATIVO)", 0, new_x="LMARGIN", new_y="NEXT", fill=True)
    
    # Cabeçalho Superior
    pdf.set_font("Helvetica", "B", 7)
    pdf.cell(50, 10, "Descrição", 1, align="C")
    pdf.cell(70, 5, "Mês Anterior", 1, align="C")
    pdf.cell(70, 5, f"Mês Atual (Até {data_hoje.strftime('%d/%m/%Y')})", 1, new_x="LMARGIN", new_y="NEXT", align="C")
    
    # Cabeçalho Inferior
    pdf.set_x(60)
    pdf.cell(20, 5, "Data", 1, align="C")
    pdf.cell(25, 5, "Planejado", 1, align="C")
    pdf.cell(25, 5, "Realizado", 1, align="C")
    pdf.cell(20, 5, "Data", 1, align="C")
    pdf.cell(25, 5, "Planejado", 1, align="C")
    pdf.cell(25, 5, "Realizado", 1, new_x="LMARGIN", new_y="NEXT", align="C")
    
    pdf.set_font("Helvetica", "", 7)
    if not gastos_excedidos:
        pdf.cell(190, 6, "Nenhum gasto acima do planejado identificado.", 1, new_x="LMARGIN", new_y="NEXT", align="C")
    else:
        for g in gastos_excedidos:
            pdf.cell(50, 6, str(g['descricao'])[:30], 1)
            # Mês Anterior
            if g.get('v_r_ant', 0) > g.get('v_p_ant', 0): pdf.set_text_color(200, 0, 0)
            pdf.cell(20, 6, g.get('dt_ant', '-'), 1, align="C")
            pdf.cell(25, 6, fmt_br(g.get('v_p_ant', 0)), 1, align="R")
            pdf.cell(25, 6, fmt_br(g.get('v_r_ant', 0)), 1, align="R")
            pdf.set_text_color(0, 0, 0)
            
            # Mês Atual
            if g.get('v_r_atu', 0) > g.get('v_p_atu', 0): pdf.set_text_color(200, 0, 0)
            pdf.cell(20, 6, g.get('dt_atu', '-'), 1, align="C")
            pdf.cell(25, 6, fmt_br(g.get('v_p_atu', 0)), 1, align="R")
            pdf.cell(25, 6, fmt_br(g.get('v_r_atu', 0)), 1, new_x="LMARGIN", new_y="NEXT", align="R")
            pdf.set_text_color(0, 0, 0)

    pdf.ln(4)

    # 3. AGENDA DE HOJE
    pdf.set_fill_color(230, 240, 255)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 8, f" 3. AGENDA FINANCEIRA DE HOJE ({data_hoje.strftime('%d/%m/%Y')})", 0, new_x="LMARGIN", new_y="NEXT", fill=True)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(90, 7, "Descrição", 1)
    pdf.cell(30, 7, "Tipo", 1)
    pdf.cell(35, 7, "Valor Previsto", 1)
    pdf.cell(35, 7, "Status", 1, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 9)
    total_hoje = 0
    if not agenda_hoje:
        pdf.cell(190, 7, "Nenhum lançamento planejado para hoje.", 1, new_x="LMARGIN", new_y="NEXT", align="C")
    else:
        for item in agenda_hoje:
            pdf.cell(90, 7, str(item['descricao'])[:45], 1)
            pdf.cell(30, 7, str(item['tipo']), 1)
            pdf.cell(35, 7, f"R$ {fmt_br(item['valor_plan'])}", 1, align="R")
            pdf.cell(35, 7, "Pendente", 1, new_x="LMARGIN", new_y="NEXT")
            total_hoje += (item['valor_plan'] or 0)

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(190, 8, f"TOTAL PARA HOJE: R$ {fmt_br(total_hoje)}", 0, new_x="LMARGIN", new_y="NEXT", align="R")

    filename = f"ORCAS_DAILY_REPORT_{usuario_nome}_{data_hoje.strftime('%Y%m%d')}.pdf"
    pdf.output(filename)
    return filename

# ==============================================================================
# FUNÇÕES DE ENVIO (E-MAIL E WHATSAPP COMENTADO)
# ==============================================================================
def enviar_email_orcas(email_destino, caminho_arquivo, usuario_nome):
    if not SMTP_SERVER or not SMTP_USER or not SMTP_PASS:
        print("Erro: Credenciais SMTP não configuradas.")
        return
        
    msg = MIMEMultipart()
    msg['From'] = f"ORCAS <{SMTP_USER}>"
    msg['To'] = email_destino
    msg['Subject'] = f"ORCAS DAILY REPORT - {usuario_nome}"

    corpo = f"Olá {usuario_nome},\n\nSegue em anexo o seu ORCAS DAILY REPORT diário.\n\nAtenciosamente,\nEquipe ORCAS."
    msg.attach(MIMEText(corpo, 'plain'))

    try:
        with open(caminho_arquivo, "rb") as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f"attachment; filename={os.path.basename(caminho_arquivo)}")
            msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT))
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
        print(f"E-mail enviado com sucesso para {email_destino}")
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")

# def enviar_zap_orcas(numero, caminho_arquivo, mensagem):
#     """
#     Função para envio via Evolution API (Mantida comentada conforme solicitado)
#     """
#     if not EVOLUTION_API_URL or not EVOLUTION_API_KEY:
#         return
#     # payload = {
#     #     "number": numero,
#     #     "mediatype": "document",
#     #     "mimetype": "application/pdf",
#     #     "caption": mensagem,
#     #     "media": base64_file
#     # }
#     # requests.post(f"{EVOLUTION_API_URL}/message/sendMedia/instancia", json=payload...)
#     pass

# ==============================================================================
# JOB PRINCIPAL - LÓGICA DE NEGÓCIO E SUPABASE
# ==============================================================================
def job_madrugada():
    if not URL or not KEY:
        print("Erro: Supabase não configurado.")
        return

    supabase = create_client(URL, KEY)
    fuso_br = timezone(timedelta(hours=-3))
    agora = datetime.now(fuso_br)
    hoje = agora.date()
    ontem = hoje - timedelta(days=1)
    
    p_mes = hoje.replace(day=1)
    p_ano = hoje.replace(month=1, day=1)
    u_mes_ant = p_mes - timedelta(days=1)
    p_mes_ant = u_mes_ant.replace(day=1)

    print(f"--- INICIANDO ROTINA INTEGRAL ORCAS: {agora.strftime('%d/%m/%Y %H:%M:%S')} ---")

    try:
        # 1. ATUALIZAÇÃO DE MÉDIA HISTÓRICA (usar_media=True)
        proximos = supabase.table("lancamentos").select("id, descricao, usuario_id")\
            .eq("usar_media", True).gte("data", hoje.strftime('%Y-%m-%d')).execute()

        if proximos.data:
            for item in proximos.data:
                hist = supabase.table("lancamentos").select("valor_real")\
                    .eq("descricao", item['descricao']).eq("usuario_id", item['usuario_id'])\
                    .eq("status", "Realizado").lt("data", hoje.strftime('%Y-%m-%d')).execute()
                
                if hist.data:
                    v_reais = [h['valor_real'] for h in hist.data if (h['valor_real'] or 0) > 0]
                    if v_reais:
                        media = sum(v_reais) / len(v_reais)
                        supabase.table("lancamentos").update({"valor_plan": round(float(media), 2)})\
                            .eq("id", item['id']).execute()
                        # 2. PROCESSAMENTO DE RESÍDUOS (Sobra de orçamento de ontem)
        lancamentos_ontem = supabase.table("lancamentos")\
            .select("*")\
            .eq("data", ontem.strftime('%Y-%m-%d'))\
            .eq("status", "Planejado")\
            .neq("regra_parcial", "Zera o Realizado")\
            .execute()

        for item in lancamentos_ontem.data:
            valor_p = float(item.get('valor_plan', 0) or 0)
            valor_r = float(item.get('valor_real', 0) or 0)
            sobra = valor_p - valor_r
            
            if sobra > 0:
                regra = item['regra_parcial']
                proximo = supabase.table("lancamentos")\
                    .select("id, valor_plan")\
                    .eq("descricao", item['descricao'])\
                    .eq("usuario_id", item['usuario_id'])\
                    .gt("data", ontem.strftime('%Y-%m-%d'))\
                    .order("data")\
                    .limit(1)\
                    .execute()

                if "Adicione a diferença" in regra and proximo.data:
                    novo_v = float(proximo.data[0]['valor_plan'] or 0) + sobra
                    supabase.table("lancamentos").update({"valor_plan": round(novo_v, 2)}).eq("id", proximo.data[0]['id']).execute()
                elif "Copia a diferença" in regra:
                    if proximo.data:
                        supabase.table("lancamentos").update({"valor_plan": round(sobra, 2)}).eq("id", proximo.data[0]['id']).execute()
                    else:
                        novo_item = item.copy()
                        novo_item.pop('id', None)
                        novo_item['data'] = hoje.strftime('%Y-%m-%d')
                        novo_item['valor_plan'] = round(sobra, 2)
                        novo_item['valor_real'] = 0.0
                        supabase.table("lancamentos").insert(novo_item).execute()

        # 3. GERAÇÃO DE RELATÓRIOS E ENVIOS POR USUÁRIO/PROJETO
        configuracoes = supabase.table("config_projetos").select("usuario_id, projeto_id, email_ativo").execute()
        
        for cfg in configuracoes.data:
            user_res = supabase.table("usuarios").select("nome, email").eq("id", cfg['usuario_id']).execute()
            if not user_res.data: continue
            
            perfil = user_res.data[0]
            lancamentos_all = supabase.table("lancamentos")\
                .select("*")\
                .eq("usuario_id", cfg['usuario_id'])\
                .eq("projeto_id", cfg['projeto_id'])\
                .execute()
            
            if lancamentos_all.data:
                # Lógica de Datas do Plano
                datas_p = [x['data'] for x in lancamentos_all.data]
                ini_p = datetime.strptime(min(datas_p), '%Y-%m-%d').date()
                fim_p = datetime.strptime(max(datas_p), '%Y-%m-%d').date()

                def calcular_periodo(s_date=None, e_date=None):
                    subset = lancamentos_all.data
                    if s_date: subset = [x for x in subset if x['data'] >= s_date.strftime('%Y-%m-%d')]
                    if e_date: subset = [x for x in subset if x['data'] <= e_date.strftime('%Y-%m-%d')]
                    return {
                        "e_p": sum([x['valor_plan'] or 0 for x in subset if x['tipo'] == 'Entrada']),
                        "e_r": sum([x['valor_real'] or 0 for x in subset if x['tipo'] == 'Entrada']),
                        "s_p": sum([x['valor_plan'] or 0 for x in subset if x['tipo'] == 'Saída']),
                        "s_r": sum([x['valor_real'] or 0 for x in subset if x['tipo'] == 'Saída']),
                        "start": s_date.strftime('%d/%m/%Y') if s_date else ini_p.strftime('%d/%m/%Y'),
                        "end": e_date.strftime('%d/%m/%Y') if e_date else fim_p.strftime('%d/%m/%Y')
                    }

                macro = {
                    "plano_hoje": calcular_periodo(ini_p, hoje),
                    "plano_total": calcular_periodo(ini_p, fim_p),
                    "mes_hoje": calcular_periodo(p_mes, hoje),
                    "mes_total": calcular_periodo(p_mes, (p_mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)),
                    "ano_hoje": calcular_periodo(p_ano, hoje),
                    "ano_total": calcular_periodo(p_ano, p_ano.replace(month=12, day=31))
                }

                # Lógica de Alertas Comparativos (Mês Anterior vs Atual)
                alertas = []
                m_atual = [x for x in lancamentos_all.data if p_mes.strftime('%Y-%m-%d') <= x['data'] <= hoje.strftime('%Y-%m-%d')]
                m_anterior = [x for x in lancamentos_all.data if p_mes_ant.strftime('%Y-%m-%d') <= x['data'] <= u_mes_ant.strftime('%Y-%m-%d')]
                
                todas_descricoes = set([x['descricao'] for x in m_atual] + [x['descricao'] for x in m_anterior])
                for d in todas_descricoes:
                    f_atu = [x for x in m_atual if x['descricao'] == d]
                    f_ant = [x for x in m_anterior if x['descricao'] == d]
                    
                    v_p_atu = sum([x['valor_plan'] or 0 for x in f_atu]); v_r_atu = sum([x['valor_real'] or 0 for x in f_atu])
                    v_p_ant = sum([x['valor_plan'] or 0 for x in f_ant]); v_r_ant = sum([x['valor_real'] or 0 for x in f_ant])
                    
                    if (v_r_atu > v_p_atu > 0) or (v_r_ant > v_p_ant > 0):
                        alertas.append({
                            'descricao': d, 
                            'dt_ant': f_ant[0]['data'] if f_ant else '-',
                            'v_p_ant': v_p_ant, 'v_r_ant': v_r_ant,
                            'dt_atu': f_atu[0]['data'] if f_atu else '-',
                            'v_p_atu': v_p_atu, 'v_r_atu': v_r_atu
                        })

                dados_hoje = [x for x in lancamentos_all.data if x['data'] == hoje.strftime('%Y-%m-%d')]
                
                pdf_path = gerar_pdf_relatorio(perfil['nome'], cfg['projeto_id'], hoje, dados_hoje, {}, macro, alertas)
                
                if cfg.get('email_ativo') == 1 and perfil.get('email'):
                    enviar_email_orcas(perfil['email'], pdf_path, perfil['nome'])
                
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)

    except Exception as e:
        print(f"Erro crítico no processamento: {e}")

    print("--- ROTINA FINALIZADA ---")

if __name__ == "__main__":
    job_madrugada()