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

# Configurações de Ambiente
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
#EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL") # Ex: https://sua-api.com
#EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY")

# Configurações de E-mail (Devem estar no GitHub Secrets)
SMTP_SERVER = os.environ.get("SMTP_SERVER")
SMTP_PORT = os.environ.get("SMTP_PORT")
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")

def fmt_br(valor):
    """Formata valor para padrão brasileiro: 1.250,55"""
    if valor is None: return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def gerar_pdf_relatorio(usuario_nome, data_hoje, agenda_hoje, resumo_ontem, analise_macro, gastos_excedidos):
    pdf = FPDF()
    pdf.add_page()
    # Trocamos Arial por Helvetica (padrão PDF) para evitar o Warning
    pdf.set_font("Helvetica", "B", 16)
    # Título com mascote estilizado
    pdf.cell(190, 10, "ORCAS DAILY REPORT  (B)", new_x="LMARGIN", new_y="NEXT", align="C")
   
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(190, 10, f"Usuário: {usuario_nome} | Data de Referência: {data_hoje.strftime('%d/%m/%Y')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    # 1. VISÃO MACRO DO PLANO (Início ao Fim)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 8, " 1. SAÚDE GERAL DO PLANO (VISÃO ACUMULADA)", 0, new_x="LMARGIN", new_y="NEXT", fill=True)
    
    # Cabeçalho da Tabela Macro (Conforme anexo solicitado)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(70, 10, "Período de Referência", 1, align="C")
    pdf.cell(60, 5, "Entradas", 1, align="C")
    pdf.cell(60, 5, "Saídas", 1, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_x(80)
    pdf.cell(30, 5, "Planejadas", 1, align="C")
    pdf.cell(30, 5, "Realizadas", 1, align="C")
    pdf.cell(30, 5, "Planejadas", 1, align="C")
    pdf.cell(30, 5, "Realizadas", 1, new_x="LMARGIN", new_y="NEXT", align="C")

    # Linhas da Tabela Macro
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
        d = analise_macro.get(key, {"e_p":0, "e_r":0, "s_p":0, "s_r":0})
        pdf.cell(70, 6, label, 1)
        pdf.cell(30, 6, fmt_br(d['e_p']), 1, align="R")
        pdf.cell(30, 6, fmt_br(d['e_r']), 1, align="R")
        pdf.cell(30, 6, fmt_br(d['s_p']), 1, align="R")
        pdf.cell(30, 6, fmt_br(d['s_r']), 1, new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.set_font("Helvetica", "I", 7)
    pdf.cell(190, 5, "OBS. O Início/Fim do Mês/Ano estão condicionados ao Início/Fim dos Planos ativos.", 0, new_x="LMARGIN", new_y="NEXT", align="R")
    
    pdf.set_font("Helvetica", "B", 10)
    # Índice de Aderência: Mede a eficiência do gasto (Realizado vs Planejado)
    aderencia = (analise_macro['plano_hoje']['s_r'] / analise_macro['plano_hoje']['s_p'] * 100) if analise_macro['plano_hoje']['s_p'] > 0 else 0
    pdf.cell(190, 8, f"Índice de Aderência ao Orçamento (Saídas Acumuladas): {aderencia:.1f}%", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # 2. GASTOS ACIMA DO PLANEJADO (MÊS ATUAL)
    meses_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_nome = meses_pt[data_hoje.month - 1]
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 8, f" 2. ALERTAS: GASTOS ACIMA DO PLANEJADO EM {mes_nome.upper()}", 0, new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(190, 5, f"Neste Mês de {mes_nome}, até o dia de hoje ({data_hoje.strftime('%d/%m/%Y')}) você teve os seguintes gastos acima do Planejado:")
    
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(80, 6, "Descrição", 1)
    pdf.cell(30, 6, "Data Origem", 1)
    pdf.cell(40, 6, "Valor Plan.", 1)
    pdf.cell(40, 6, "Valor Real (Acum.)", 1, new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "", 8)
    if not gastos_excedidos:
        pdf.cell(190, 6, "Nenhum gasto acima do planejado identificado neste período.", 1, new_x="LMARGIN", new_y="NEXT", align="C")
    else:
        for g in gastos_excedidos:
            pdf.cell(80, 6, str(g['descricao'])[:40], 1)
            pdf.cell(30, 6, g['data'], 1)
            pdf.cell(40, 6, fmt_br(g['v_p']), 1, align="R")
            pdf.cell(40, 6, fmt_br(g['v_r']), 1, new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.ln(4)

    # 3. AGENDA DE HOJE
    pdf.set_fill_color(230, 240, 255)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 8, f" 3. AGENDA FINANCEIRA DE HOJE ({data_hoje.strftime('%d/%m/%Y')})", 0, new_x="LMARGIN", new_y="NEXT", fill=True)
    
    # Cabeçalho Tabela
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(90, 7, "Descrição", 1)
    pdf.cell(30, 7, "Tipo", 1)
    pdf.cell(35, 7, "Valor Previsto", 1)
    pdf.cell(35, 7, "Status", 1, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 9)
    total_hoje = 0
    for item in agenda_hoje[:15]:
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

# =================================================================
# TITULO: LOGICA DE ENVIO PARA WHATSAPP (EVOLUTION API)
# ESTE CODIGO ESTA PRONTO PARA USO, MAS COMENTADO POR SEGURANÇA
# =================================================================
#def enviar_whatsapp_evolution(numero, caminho_arquivo):
#    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY:
#        return
#    
#    url = f"{EVOLUTION_API_URL}/message/sendMedia/instancia_orcas"
#    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
#    
#    try:
#        with open(caminho_arquivo, "rb") as f:
#            import base64
#            encoded_pdf = base64.b64encode(f.read()).decode('utf-8')
#
#        payload = {
#            "number": numero,
#            "media": f"data:application/pdf;base64,{encoded_pdf}",
#            "mediatype": "document",
#            "caption": "📊 Seu ORCAS DAILY REPORT está pronto!",
#            "fileName": "ORCAS_DAILY_REPORT.pdf"
#        }
#        requests.post(url, json=payload, headers=headers)
#    except Exception as e:
#        print(f"Erro ao enviar WhatsApp para {numero}: {e}")

def enviar_email_orcas(email_destino, caminho_arquivo, usuario_nome):
    print(f"DEBUG: Tentando enviar e-mail para {email_destino}...")
    if not SMTP_SERVER or not SMTP_USER or not SMTP_PASS:
        print("ERRO: Credenciais de SMTP não encontradas no GitHub Secrets!")
        return

    msg = MIMEMultipart()
    msg['From'] = f"ORCAS <{SMTP_USER}>"
    msg['To'] = email_destino
    msg['Subject'] = f"ORCAS DAILY REPORT - {usuario_nome}"

    corpo = f"Olá {usuario_nome},\n\nSegue em anexo o seu ORCAS DAILY REPORT com a visão macro da sua saúde financeira e agenda de hoje."
    msg.attach(MIMEText(corpo, 'plain'))

    with open(caminho_arquivo, "rb") as attachment:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename=ORCAS_DAILY_REPORT.pdf")
        msg.attach(part)

    try:
        server = smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT))
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Erro ao enviar E-mail para {email_destino}: {e}")

def job_madrugada():
    if not URL or not KEY:
        print("ERRO: VARIÁVEIS DE AMBIENTE (SUPABASE) NÃO ENCONTRADAS.")
        return

    supabase = create_client(URL, KEY)
    
    fuso_br = timezone(timedelta(hours=-3))
    agora = datetime.now(fuso_br)
    hoje = agora.date()
    ontem = hoje - timedelta(days=1)
    primeiro_dia_mes = hoje.replace(day=1)
    primeiro_dia_ano = hoje.replace(month=1, day=1)
    
    print(f"--- INICIANDO ROTINA ORCAS (BATCH 3AM): {hoje.strftime('%d/%m/%Y')} ---")

    try:
        # --- 1. PROCESSAR MÉDIA HISTÓRICA TOTAL ---
        proximos = supabase.table("lancamentos")\
            .select("id, descricao, usuario_id")\
            .eq("usar_media", True)\
            .gte("data", hoje.strftime('%Y-%m-%d'))\
            .execute()

        if proximos.data:
            descricoes_unicas = set((x['descricao'], x['usuario_id']) for x in proximos.data)

            for desc, user_id in descricoes_unicas:
                historico = supabase.table("lancamentos")\
                    .select("valor_real")\
                    .eq("descricao", desc)\
                    .eq("usuario_id", user_id)\
                    .eq("status", "Realizado")\
                    .lt("data", hoje.strftime('%Y-%m-%d'))\
                    .execute()
                
                if historico.data:
                    valores = [h['valor_real'] for h in historico.data if h['valor_real'] > 0]
                    if valores:
                        media_total = sum(valores) / len(valores)
                        
                        supabase.table("lancamentos")\
                            .update({"valor_plan": round(float(media_total), 2)})\
                            .eq("descricao", desc)\
                            .eq("usuario_id", user_id)\
                            .eq("usar_media", True)\
                            .eq("status", "Planejado")\
                            .gte("data", hoje.strftime('%Y-%m-%d'))\
                            .execute()
                        print(f"MÉDIA HISTÓRICA ATUALIZADA: {desc} -> R$ {media_total:.2f}")

        # --- 2. PROCESSAR RESÍDUOS ---
        residuos = supabase.table("lancamentos")\
            .select("*")\
            .eq("data", ontem.strftime('%Y-%m-%d'))\
            .eq("status", "Planejado")\
            .neq("regra_parcial", "Zera o Realizado")\
            .execute()

        for item in residuos.data:
            valor_p = float(item.get('valor_plan', 0))
            valor_r = float(item.get('valor_real', 0))
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

                if "Adicione a diferença" in regra:
                    if proximo.data:
                        novo_v = float(proximo.data[0]['valor_plan']) + sobra
                        supabase.table("lancamentos")\
                            .update({"valor_plan": round(novo_v, 2)}).eq("id", proximo.data[0]['id']).execute()
                        print(f"RESÍDUO ADICIONADO: {item['descricao']} (+ R$ {sobra:.2f})")

                elif "Copia a diferença" in regra:
                    if proximo.data:
                        supabase.table("lancamentos")\
                            .update({"valor_plan": round(sobra, 2)}).eq("id", proximo.data[0]['id']).execute()
                        print(f"RESÍDUO COPIADO (Substituição): {item['descricao']} (R$ {sobra:.2f} transferido)")
                    else:
                        novo_item = item.copy()
                        novo_item.pop('id', None)
                        novo_item['data'] = hoje.strftime('%Y-%m-%d')
                        novo_item['valor_plan'] = round(sobra, 2)
                        novo_item['valor_real'] = 0.0
                        supabase.table("lancamentos").insert(novo_item).execute()
                        print(f"RESÍDUO COPIADO (Criação): {item['descricao']} (R$ {sobra:.2f} criado para hoje)")

        # --- 3. GERAÇÃO E ENVIO DE RELATÓRIO PDF ---
        config_envios = supabase.table("config_projetos").select("usuario_id, projeto_id, zap_ativo, email_ativo").execute()

        if config_envios.data:
            for cfg in config_envios.data:
                res_user = supabase.table("usuarios").select("nome, email, celular").eq("id", cfg['usuario_id']).execute()
                
                if res_user.data:
                    perfil = res_user.data[0]
                    nome_usuario = perfil.get('nome') if perfil.get('nome') else "Usuario"
                    
                    # BUSCA TODOS OS DADOS DO PROJETO PARA CÁLCULOS MACRO
                    all_data = supabase.table("lancamentos").select("tipo, valor_plan, valor_real, data, parcial_real, permite_parciais, descricao")\
                        .eq("usuario_id", cfg['usuario_id']).eq("projeto_id", cfg['projeto_id']).execute()
                    
                    if not all_data.data: continue

                    def calc_periodo(start_date=None, end_date=None):
                        subset = all_data.data
                        if start_date: subset = [x for x in subset if x['data'] >= start_date.strftime('%Y-%m-%d')]
                        if end_date: subset = [x for x in subset if x['data'] <= end_date.strftime('%Y-%m-%d')]
                        
                        return {
                            "e_p": sum([x['valor_plan'] or 0 for x in subset if x['tipo'] == 'Entrada']),
                            "e_r": sum([x['valor_real'] or 0 for x in subset if x['tipo'] == 'Entrada']),
                            "s_p": sum([x['valor_plan'] or 0 for x in subset if x['tipo'] == 'Saída']),
                            "s_r": sum([x['valor_real'] or 0 for x in subset if x['tipo'] == 'Saída'])
                        }

                    analise_macro = {
                        "plano_hoje": calc_periodo(None, hoje),
                        "plano_total": calc_periodo(None, None),
                        "mes_hoje": calc_periodo(primeiro_dia_mes, hoje),
                        "mes_total": calc_periodo(primeiro_dia_mes, primeiro_dia_mes + timedelta(days=31)),
                        "ano_hoje": calc_periodo(primeiro_dia_ano, hoje),
                        "ano_total": calc_periodo(primeiro_dia_ano, primeiro_dia_ano.replace(month=12, day=31))
                    }

                    # LOGICA DE GASTOS EXCEDIDOS NO MÊS (SAÍDA REALIZADO > PLANEJADO)
                    gastos_excedidos = []
                    mes_data = [x for x in all_data.data if x['data'] >= primeiro_dia_mes.strftime('%Y-%m-%d') and x['data'] <= hoje.strftime('%Y-%m-%d') and x['tipo'] == 'Saída']
                    
                    # Filtra registros base que possuem o checkbox "permite parciais"
                    for item in [x for x in mes_data if x.get('permite_parciais')]:
                        # Soma parciais de TODOS os registros com a mesma descrição no período
                        tot_parcial = sum([p['parcial_real'] or 0 for p in mes_data if p['descricao'] == item['descricao']])
                        if tot_parcial > (item['valor_plan'] or 0):
                            gastos_excedidos.append({
                                'descricao': item['descricao'], 
                                'data': datetime.strptime(item['data'], '%Y-%m-%d').strftime('%d/%m/%Y'), 
                                'v_p': item['valor_plan'], 
                                'v_r': tot_parcial
                            })
                    
                    # Itens normais (sem parciais)
                    for item in [x for x in mes_data if not x.get('permite_parciais')]:
                        if (item['valor_real'] or 0) > (item['valor_plan'] or 0):
                            gastos_excedidos.append({
                                'descricao': item['descricao'], 
                                'data': datetime.strptime(item['data'], '%Y-%m-%d').strftime('%d/%m/%Y'), 
                                'v_p': item['valor_plan'], 
                                'v_r': item['valor_real']
                            })

                    # BUSCA ONTEM (Fechamento)
                    dados_ontem = [x for x in all_data.data if x['data'] == ontem.strftime('%Y-%m-%d')]
                    resumo_ontem = {
                        "data": ontem.strftime('%d/%m/%Y'),
                        "total_p": sum([x['valor_plan'] or 0 for x in dados_ontem]),
                        "total_r": sum([x['valor_real'] or 0 for x in dados_ontem])
                    }

                    # BUSCA HOJE (Agenda)
                    dados_hoje = [x for x in all_data.data if x['data'] == hoje.strftime('%Y-%m-%d')]

                    if dados_hoje:
                        pdf_path = gerar_pdf_relatorio(nome_usuario, hoje, dados_hoje, resumo_ontem, analise_macro, gastos_excedidos)
                        
                        if cfg.get('email_ativo') == 1 and perfil.get('email'):
                            enviar_email_orcas(perfil['email'], pdf_path, nome_usuario)
                            print(f"RELATÓRIO E-MAIL ENVIADO: {nome_usuario}")

                        if os.path.exists(pdf_path):
                            os.remove(pdf_path)

    except Exception as e:
        print(f"ERRO DURANTE A EXECUÇÃO: {e}")

    print(f"--- ROTINA FINALIZADA ÀS {datetime.now(fuso_br).strftime('%H:%M:%S')} ---")

if __name__ == "__main__":
    job_madrugada()