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

def gerar_pdf_relatorio(usuario_nome, data_ref, lancamentos):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(190, 10, "RELATÓRIO DIÁRIO ORCAS", ln=True, align="C")
    pdf.set_font("Arial", "", 12)
    pdf.cell(190, 10, f"Usuário: {usuario_nome} | Data: {data_ref.strftime('%d/%m/%Y')}", ln=True, align="C")
    pdf.ln(10)

    # Cabeçalho Tabela
    pdf.set_font("Arial", "B", 10)
    pdf.cell(80, 8, "Descrição", 1)
    pdf.cell(30, 8, "Tipo", 1)
    pdf.cell(40, 8, "Planejado", 1)
    pdf.cell(40, 8, "Realizado", 1, ln=True)

    pdf.set_font("Arial", "", 10)
    total_p = 0
    total_r = 0

    for item in lancamentos:
        pdf.cell(80, 8, str(item['descricao'])[:40], 1)
        pdf.cell(30, 8, str(item['tipo']), 1)
        pdf.cell(40, 8, f"R$ {item['valor_plan']:.2f}", 1)
        pdf.cell(40, 8, f"R$ {item['valor_real']:.2f}", 1, ln=True)
        total_p += item['valor_plan']
        total_r += item['valor_real']

    pdf.ln(5)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(110, 8, "TOTAIS DO PERÍODO", 1)
    pdf.cell(40, 8, f"R$ {total_p:.2f}", 1)
    pdf.cell(40, 8, f"R$ {total_r:.2f}", 1, ln=True)

    filename = f"relatorio_{usuario_nome}_{data_ref.strftime('%Y%m%d')}.pdf"
    pdf.output(filename)
    return filename

def enviar_whatsapp_evolution(numero, caminho_arquivo):
    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY:
        return
    
    url = f"{EVOLUTION_API_URL}/message/sendMedia/instancia_orcas"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    
    with open(caminho_arquivo, "rb") as f:
        import base64
        encoded_pdf = base64.b64encode(f.read()).decode('utf-8')

    payload = {
        "number": numero,
        "media": f"data:application/pdf;base64,{encoded_pdf}",
        "mediatype": "document",
        "caption": "📊 Seu relatório diário ORCAS está pronto!",
        "fileName": "Relatorio_Orcas.pdf"
    }
    
    try:
        requests.post(url, json=payload, headers=headers)
    except:
        print(f"Erro ao enviar WhatsApp para {numero}")

def enviar_email_orcas(email_destino, caminho_arquivo, usuario_nome):
    if not SMTP_SERVER or not SMTP_USER or not SMTP_PASS:
        return

    msg = MIMEMultipart()
    msg['From'] = f"ORCAS <{SMTP_USER}>"
    msg['To'] = email_destino
    msg['Subject'] = f"Relatório Diário ORCAS - {usuario_nome}"

    corpo = f"Olá {usuario_nome},\n\nSegue em anexo o seu Relatório Diário ORCAS preparado nesta madrugada."
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
        # Busca configurações de projetos/planos para saber quem deve receber
        config_envios = supabase.table("config_projetos").select("usuario_id, projeto_id, zap_ativo, email_ativo").execute()

        if config_envios.data:
            for cfg in config_envios.data:
                # Coleta dados do perfil para e-mail e telefone
                user_perfil = supabase.table("perfis").select("nome, email, telefone").eq("id", cfg['usuario_id']).execute()
                
                if user_perfil.data:
                    perfil = user_perfil.data[0]
                    dados_rel = supabase.table("lancamentos")\
                        .select("descricao, tipo, valor_plan, valor_real")\
                        .eq("usuario_id", cfg['usuario_id'])\
                        .eq("projeto_id", cfg['projeto_id'])\
                        .eq("data", ontem.strftime('%Y-%m-%d'))\
                        .execute()

                    if dados_rel.data:
                        pdf_path = gerar_pdf_relatorio(perfil['nome'], ontem, dados_rel.data)
                        
                        # Lógica de Envio por E-mail
                        if cfg.get('email_ativo') == 1 and perfil.get('email'):
                            enviar_email_orcas(perfil['email'], pdf_path, perfil['nome'])
                            print(f"RELATÓRIO E-MAIL ENVIADO: {perfil['nome']}")

                        # Lógica de Envio por WhatsApp (COMENTADO conforme solicitação)
                        # if cfg.get('zap_ativo') == 1 and perfil.get('telefone'):
                        #     enviar_whatsapp_evolution(perfil['telefone'], pdf_path)
                        #     print(f"RELATÓRIO WHATSAPP ENVIADO: {perfil['nome']}")
                        
                        if os.path.exists(pdf_path):
                            os.remove(pdf_path)

    except Exception as e:
        print(f"ERRO DURANTE A EXECUÇÃO: {e}")

    print(f"--- ROTINA FINALIZADA ÀS {datetime.now(fuso_br).strftime('%H:%M:%S')} ---")

if __name__ == "__main__":
    job_madrugada()