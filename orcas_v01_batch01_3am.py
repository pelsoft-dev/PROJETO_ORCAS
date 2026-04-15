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
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def gerar_pdf_relatorio(usuario_nome, data_hoje, agenda_hoje, resumo_ontem, analise_macro):
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
    pdf.set_font("Helvetica", "", 10)
    
    aderencia = (analise_macro['realizado'] / analise_macro['planejado'] * 100) if analise_macro['planejado'] > 0 else 0
    pdf.cell(95, 8, f"Total Planejado no Plano: R$ {fmt_br(analise_macro['planejado'])}")
    pdf.cell(95, 8, f"Total Realizado até agora: R$ {fmt_br(analise_macro['realizado'])}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(190, 8, f"Índice de Aderência ao Orçamento: {aderencia:.1f}%", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # 2. FECHAMENTO DE ONTEM
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 8, " 2. FECHAMENTO DO DIA ANTERIOR", 0, new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(190, 8, f"Ontem ({resumo_ontem['data']}): Planejado R$ {fmt_br(resumo_ontem['total_p'])} | Realizado R$ {fmt_br(resumo_ontem['total_r'])}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

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
    for item in agenda_hoje[:18]: # Limite para não estourar a página
        pdf.cell(90, 7, str(item['descricao'])[:45], 1)
        pdf.cell(30, 7, str(item['tipo']), 1)
        pdf.cell(35, 7, f"R$ {fmt_br(item['valor_plan'])}", 1)
        pdf.cell(35, 7, "Pendente", 1, new_x="LMARGIN", new_y="NEXT")
        total_hoje += item['valor_plan']

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(190, 8, f"TOTAL PARA HOJE: R$ {fmt_br(total_hoje)}", 0, new_x="LMARGIN", new_y="NEXT", align="R")

    filename = f"relatorio_{usuario_nome}_{data_hoje.strftime('%Y%m%d')}.pdf"
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
#            "caption": "📊 Seu relatório diário ORCAS está pronto!",
#            "fileName": "Relatorio_Orcas.pdf"
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
    msg['Subject'] = f"Relatório Estrategista ORCAS - {usuario_nome}"

    corpo = f"Olá {usuario_nome},\n\nSegue em anexo o seu Relatório Estrategista ORCAS (Uma Página) com visão macro do plano e agenda de hoje."
    msg.attach(MIMEText(corpo, 'plain'))

    with open(caminho_arquivo, "rb") as attachment:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename=Relatorio_Orcas.pdf")
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
                    
                    # BUSCA MACRO (24 Meses)
                    macro_data = supabase.table("lancamentos").select("valor_plan, valor_real")\
                        .eq("usuario_id", cfg['usuario_id']).eq("projeto_id", cfg['projeto_id']).execute()
                    
                    total_plan = sum([x['valor_plan'] for x in macro_data.data if x['valor_plan']])
                    total_real = sum([x['valor_real'] for x in macro_data.data if x['valor_real']])
                    
                    analise_macro = {"planejado": total_plan, "realizado": total_real}

                    # BUSCA ONTEM (Fechamento)
                    dados_ontem = supabase.table("lancamentos").select("valor_plan, valor_real")\
                        .eq("usuario_id", cfg['usuario_id']).eq("data", ontem.strftime('%Y-%m-%d')).execute()
                    resumo_ontem = {
                        "data": ontem.strftime('%d/%m/%Y'),
                        "total_p": sum([x['valor_plan'] for x in dados_ontem.data]),
                        "total_r": sum([x['valor_real'] for x in dados_ontem.data])
                    }

                    # BUSCA HOJE (Agenda)
                    dados_hoje = supabase.table("lancamentos")\
                        .select("descricao, tipo, valor_plan")\
                        .eq("usuario_id", cfg['usuario_id'])\
                        .eq("projeto_id", cfg['projeto_id'])\
                        .eq("data", hoje.strftime('%Y-%m-%d'))\
                        .execute()

                    if dados_hoje.data:
                        pdf_path = gerar_pdf_relatorio(nome_usuario, hoje, dados_hoje.data, resumo_ontem, analise_macro)
                        
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