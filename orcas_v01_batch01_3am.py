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
EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL") # Ex: https://sua-api.com
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY")

# Configurações de E-mail (Devem estar no GitHub Secrets)
SMTP_SERVER = os.environ.get("SMTP_SERVER")
SMTP_PORT = os.environ.get("SMTP_PORT")
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")

def fmt_br(valor):
    """Formata valor para padrão brasileiro: 1.250,55"""
    if valor is None: return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def gerar_pdf_relatorio(usuario_nome, nome_plano, data_hoje, agenda_hoje, resumo_ontem, analise_macro, gastos_excedidos):
    pdf = FPDF()
    pdf.add_page()
    
    # 2) INCLUIR A FIGURA DA BALEIA QUE ESTÁ NO ANEXO01 NO TOPO, A ESQUERDA
    # Certifique-se de que o arquivo 'orca_mascote.png' está na raiz do seu repositório
    if os.path.exists("orca_mascote.png"):
        pdf.image("orca_mascote.png", x=10, y=8, w=22)
    
    # Trocamos Arial por Helvetica (padrão PDF) para evitar o Warning
    pdf.set_font("Helvetica", "B", 16)
    
    # 3) RETIRE O “(B)” QUE ESTÁ NO TÍTULO.
    pdf.cell(190, 10, "ORCAS DAILY REPORT", new_x="LMARGIN", new_y="NEXT", align="C")
    
    pdf.set_font("Helvetica", "", 10)
    
    # 4) TROCAR “DATA DE REFERÊNCIA” POR “DATA” NO SUB-TÍTULO
    # 5) INCLUA NO SUB-TÍTULO, ENTRE O USUÁRIO E A DATA, O “PLANO: nome-do-plano”
    subtitulo = f"Usuário: {usuario_nome} | PLANO: {nome_plano} | Data: {data_hoje.strftime('%d/%m/%Y')}"
    pdf.cell(190, 10, subtitulo, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    # 1. VISÃO MACRO DO PLANO (Tabela conforme anexo)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 8, " 1. SAÚDE GERAL DO PLANO (VISÃO ACUMULADA)", 0, new_x="LMARGIN", new_y="NEXT", fill=True)
    
    # Cabeçalho da Tabela Macro
    # 6) NO ITEM “1. SAÚDE GERAL DO PLANO”, INCLUIR AS DATAS CONFORME O ANEXO02.
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

    # Linhas da Tabela Macro
    pdf.set_font("Helvetica", "", 7)
    periodos = [
        ("Início do Plano até Hoje", "plano_hoje"),
        ("Início do Plano até o Fim do Plano", "plano_total"),
        ("Início do Mês até Hoje", "mes_hoje"),
        ("Início do Mês até o Fim do Mês", "mes_total"),
        ("Início do Ano até Hoje", "ano_hoje"),
        ("Início do Ano até o Fim do Ano", "ano_total")
    ]

    for label, key in periodos:
        d = analise_macro.get(key, {"e_p":0, "e_r":0, "s_p":0, "s_r":0, "start": "-", "end": "-"})
        pdf.cell(45, 6, label, 1)
        pdf.cell(35, 6, f"{d['start']} a {d['end']}", 1, align="C")
        pdf.cell(27.5, 6, fmt_br(d['e_p']), 1, align="R")
        pdf.cell(27.5, 6, fmt_br(d['e_r']), 1, align="R")
        pdf.cell(27.5, 6, fmt_br(d['s_p']), 1, align="R")
        pdf.cell(27.5, 6, fmt_br(d['s_r']), 1, new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    # Índice de Aderência: Focado em Saídas Acumuladas (Realizado vs Planejado)
    aderencia = (analise_macro['plano_hoje']['s_r'] / analise_macro['plano_hoje']['s_p'] * 100) if analise_macro['plano_hoje']['s_p'] > 0 else 0
    pdf.cell(190, 8, f"Índice de Aderência ao Orçamento (Saídas Acumuladas): {aderencia:.1f}%", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # 7) NO ITEM “2. ALERTAS: GASTOS ACIMA DO PLANEJADO (COMPARATIVO)” 
    # MUDAR PARA O FORMATO EXATO DO MOSTRADO NO ANEXO03
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 8, " 2. ALERTAS: GASTOS ACIMA DO PLANEJADO (COMPARATIVO)", 0, new_x="LMARGIN", new_y="NEXT", fill=True)
    
    pdf.set_font("Helvetica", "B", 7)
    pdf.cell(60, 6, "Descrição", 1, align="C")
    pdf.cell(20, 6, "Data", 1, align="C")
    pdf.cell(27, 6, "Plan. Mês Ant.", 1, align="C")
    pdf.cell(27, 6, "Real. Mês Ant.", 1, align="C")
    pdf.cell(27, 6, "Plan. Atual", 1, align="C")
    pdf.cell(27, 6, "Real. Atual", 1, new_x="LMARGIN", new_y="NEXT", align="C")
    
    pdf.set_font("Helvetica", "", 7)
    if not gastos_excedidos:
        pdf.cell(190, 6, "Nenhum gasto acima do planejado identificado.", 1, new_x="LMARGIN", new_y="NEXT", align="C")
    else:
        for g in gastos_excedidos:
            pdf.set_text_color(200, 0, 0) # LISTADAS EM VERMELHO
            pdf.cell(60, 6, str(g['descricao'])[:35], 1)
            pdf.cell(20, 6, g['data_ref'], 1, align="C")
            pdf.cell(27, 6, fmt_br(g['v_p_ant']), 1, align="R")
            pdf.cell(27, 6, fmt_br(g['v_r_ant']), 1, align="R")
            pdf.cell(27, 6, fmt_br(g['v_p_atu']), 1, align="R")
            pdf.cell(27, 6, fmt_br(g['v_r_atu']), 1, new_x="LMARGIN", new_y="NEXT", align="R")
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

    try:
        with open(caminho_arquivo, "rb") as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f"attachment; filename=ORCAS_DAILY_REPORT.pdf")
            msg.attach(part)

        # Ajuste para não travar: Timeout de 30s e Debug Level
        server = smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT), timeout=30)
        server.set_debuglevel(1) 
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
        print(f"SUCESSO: E-mail enviado para {email_destino}")
    except Exception as e:
        print(f"ERRO AO ENVIAR E-MAIL: {e}")

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
    
    # Referências para Mês Anterior (Item 7)
    ultimo_dia_mes_ant = primeiro_dia_mes - timedelta(days=1)
    primeiro_dia_mes_ant = ultimo_dia_mes_ant.replace(day=1)
    
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
                proximo = supabase.table("lancamentos")\
                    .select("id, valor_plan")\
                    .eq("descricao", item['descricao'])\
                    .eq("usuario_id", item['usuario_id'])\
                    .gt("data", ontem.strftime('%Y-%m-%d'))\
                    .order("data")\
                    .limit(1)\
                    .execute()

                if "Adicione a diferença" in item['regra_parcial'] and proximo.data:
                    novo_v = float(proximo.data[0]['valor_plan']) + sobra
                    supabase.table("lancamentos").update({"valor_plan": round(novo_v, 2)}).eq("id", proximo.data[0]['id']).execute()
                elif "Copia a diferença" in item['regra_parcial']:
                    if proximo.data:
                        supabase.table("lancamentos").update({"valor_plan": round(sobra, 2)}).eq("id", proximo.data[0]['id']).execute()
                    else:
                        novo_item = item.copy()
                        novo_item.pop('id', None)
                        novo_item['data'] = hoje.strftime('%Y-%m-%d')
                        novo_item['valor_plan'] = round(sobra, 2)
                        novo_item['valor_real'] = 0.0
                        supabase.table("lancamentos").insert(novo_item).execute()

        # --- 3. GERAÇÃO E ENVIO DE RELATÓRIO PDF ---
        config_envios = supabase.table("config_projetos").select("usuario_id, projeto_id, zap_ativo, email_ativo").execute()

        if config_envios.data:
            for cfg in config_envios.data:
                res_user = supabase.table("usuarios").select("nome, email, celular").eq("id", cfg['usuario_id']).execute()
                
                if res_user.data:
                    perfil = res_user.data[0]
                    nome_usuario = perfil.get('nome', "Usuario")
                    nome_plano = cfg.get('projeto_id', "Geral")
                    
                    raw_data = supabase.table("lancamentos").select("*")\
                        .eq("usuario_id", cfg['usuario_id']).eq("projeto_id", cfg['projeto_id']).execute()
                    all_lancs = raw_data.data if raw_data.data else []

                    # Datas do Plano para Tabela 1
                    plan_ini_str = min([x['data'] for x in all_lancs]) if all_lancs else hoje.strftime('%Y-%m-%d')
                    plan_ini = datetime.strptime(plan_ini_str, '%Y-%m-%d').date()
                    plan_fim_str = max([x['data'] for x in all_lancs]) if all_lancs else hoje.strftime('%Y-%m-%d')

                    def calc_periodo(sd, ed):
                        subset = [x for x in all_lancs if (not sd or x['data'] >= sd.strftime('%Y-%m-%d')) and (not ed or x['data'] <= ed.strftime('%Y-%m-%d'))]
                        return {
                            "e_p": sum([x['valor_plan'] or 0 for x in subset if x['tipo'] == 'Entrada']),
                            "e_r": sum([x['valor_real'] or 0 for x in subset if x['tipo'] == 'Entrada']),
                            "s_p": sum([x['valor_plan'] or 0 for x in subset if x['tipo'] == 'Saída']),
                            "s_r": sum([x['valor_real'] or 0 for x in subset if x['tipo'] == 'Saída']),
                            "start": sd.strftime('%d/%m/%Y') if sd else plan_ini.strftime('%d/%m/%Y'),
                            "end": ed.strftime('%d/%m/%Y') if ed else plan_fim_str.split('-')[2]+'/'+plan_fim_str.split('-')[1]+'/'+plan_fim_str.split('-')[0]
                        }

                    analise_macro = {
                        "plano_hoje": calc_periodo(plan_ini, hoje),
                        "plano_total": calc_periodo(plan_ini, None),
                        "mes_hoje": calc_periodo(primeiro_dia_mes, hoje),
                        "mes_total": calc_periodo(primeiro_dia_mes, primeiro_dia_mes.replace(day=28) + timedelta(days=4)),
                        "ano_hoje": calc_periodo(primeiro_dia_ano, hoje),
                        "ano_total": calc_periodo(primeiro_dia_ano, primeiro_dia_ano.replace(month=12, day=31))
                    }

                    # 7) LÓGICA DE GASTOS EXCEDIDOS COMPARATIVO
                    alertas_excedidos = []
                    atu_l = [x for x in all_lancs if x['data'] >= primeiro_dia_mes.strftime('%Y-%m-%d') and x['data'] <= hoje.strftime('%Y-%m-%d') and x['tipo'] == 'Saída']
                    ant_l = [x for x in all_lancs if x['data'] >= primeiro_dia_mes_ant.strftime('%Y-%m-%d') and x['data'] <= ultimo_dia_mes_ant.strftime('%Y-%m-%d') and x['tipo'] == 'Saída']
                    
                    for desc in set([x['descricao'] for x in atu_l] + [x['descricao'] for x in ant_l]):
                        atu_items = [x for x in atu_l if x['descricao'] == desc]
                        vpa_atu = sum([x['valor_plan'] or 0 for x in atu_items])
                        vra_atu = sum([(x['parcial_real'] if x.get('permite_parcial') else x['valor_real']) or 0 for x in atu_items])
                        
                        ant_items = [x for x in ant_l if x['descricao'] == desc]
                        vpa_ant = sum([x['valor_plan'] or 0 for x in ant_items])
                        vra_ant = sum([(x['parcial_real'] if x.get('permite_parcial') else x['valor_real']) or 0 for x in ant_items])
                        
                        if (vra_atu > vpa_atu and vpa_atu > 0) or (vra_ant > vpa_ant and vpa_ant > 0):
                            parciais_d = [x.get('parcial_data') for x in atu_items if x.get('parcial_data')]
                            final_d = max(parciais_d) if parciais_d else (atu_items[0]['data'] if atu_items else hoje.strftime('%Y-%m-%d'))
                            
                            alertas_excedidos.append({
                                'descricao': desc, 'data_ref': datetime.strptime(final_d, '%Y-%m-%d').strftime('%d/%m/%Y'),
                                'v_p_ant': vpa_ant, 'v_r_ant': vra_ant, 'v_p_atu': vpa_atu, 'v_r_atu': vra_atu
                            })

                    # 1) O RELATÓRIO DEVE SER GERADO INDEPENDENTE SE EXISTAM LANÇAMENTOS NO DIA OU NÃO
                    dados_hoje = [x for x in all_lancs if x['data'] == hoje.strftime('%Y-%m-%d')]
                    pdf_path = gerar_pdf_relatorio(nome_usuario, nome_plano, hoje, dados_hoje, None, analise_macro, alertas_excedidos)
                    
                    if cfg.get('email_ativo') == 1 and perfil.get('email'):
                        enviar_email_orcas(perfil['email'], pdf_path, nome_usuario)
                    
                    if os.path.exists(pdf_path): os.remove(pdf_path)

    except Exception as e:
        print(f"ERRO CRÍTICO NA ROTINA: {e}")

    print(f"--- ROTINA FINALIZADA ÀS {datetime.now(fuso_br).strftime('%H:%M:%S')} ---")

if __name__ == "__main__":
    job_madrugada()