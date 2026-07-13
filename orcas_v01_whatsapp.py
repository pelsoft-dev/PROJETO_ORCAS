#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORCAS SaaS - Módulo de Notificação Batch de Madrugada via WhatsApp
Arquivo: orcas_v01_whatsapp.py
"""

import sys
import httpx
import os
import base64
from datetime import datetime
from supabase import create_client, Client

def executar_envio_diario():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando processamento de notificações...")

    # 1. Conexão Segura com o Supabase usando variáveis de ambiente ou arquivo local
    try:
        import streamlit as st
        # Se executado em contexto que lê st.secrets
        SUPABASE_URL = st.secrets["SUPABASE_URL"]
        SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
        EVOLUTION_API_URL = st.secrets.get("EVOLUTION_API_URL", "http://localhost:8080")
        EVOLUTION_API_KEY = st.secrets.get("EVOLUTION_API_KEY", "SUA_API_KEY_AQUI")
        EVOLUTION_INSTANCE = st.secrets.get("EVOLUTION_INSTANCE", "orcas_instance")
        APP_URL_BASE = "https://orcas-planejamento-financiero.streamlit.app"
    except Exception:
        # Fallback para execução CRON direta/Batch puro usando OS Environment
        SUPABASE_URL = os.getenv("SUPABASE_URL")
        SUPABASE_KEY = os.getenv("SUPABASE_KEY")
        EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
        EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "SUA_API_KEY_AQUI")
        EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "orcas_instance")
        APP_URL_BASE = "https://orcas-planejamento-financiero.streamlit.app"

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Erro: Credenciais do Supabase não configuradas no ambiente.")
        sys.exit(1)

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 2. Definição dos parâmetros temporais do Batch (Fuso Corrente)
    hoje = datetime.now().date()
    hoje_str = hoje.strftime('%Y-%m-%d')
    mes_corrente = hoje.month
    ano_corrente = hoje.year

    # 3. Busca de Usuários Ativos
    try:
        usuarios_req = supabase.table("usuarios").select("id, email, celular, vencimento").execute()
        usuarios = usuarios_req.data if usuarios_req.data else []
    except Exception as e:
        print(f"Erro ao buscar usuários no Supabase: {e}")
        return

    print(f"Total de {len(usuarios)} contas verificadas na base de dados.")

    # 4. Processamento de Lançamentos por Usuário
    for user in usuarios:
        user_id = user.get("id")
        celular = user.get("celular")
        email = user.get("email")
        vencimento_usuario = user.get("vencimento")

        if not celular or str(celular).strip() == "":
            continue

        if vencimento_usuario:
            try:
                if datetime.strptime(vencimento_usuario, '%Y-%m-%d').date() < hoje:
                    continue
            except Exception:
                pass

        try:
            lanc_req = supabase.table("lancamentos").select("*").eq("usuario_id", user_id).execute()
            all_lancamentos = lanc_req.data if lanc_req.data else []
        except Exception as e:
            print(f"Erro ao coletar lançamentos do usuário {email}: {e}")
            continue

        filtrados = []
        for l in all_lancamentos:
            if l.get("data") == hoje_str:
                filtrados.append(l)
                continue
            
            if l.get("permite_parcial") is True and l.get("data_vencimento"):
                try:
                    dt_venc = datetime.strptime(l["data_vencimento"], '%Y-%m-%d').date()
                    if dt_venc.month == mes_corrente and dt_venc.year == ano_corrente:
                        filtrados.append(l)
                except ValueError:
                    pass

        if len(filtrados) > 0:
            total_entradas = sum(float(x.get('valor_plan', 0)) for x in filtrados if x.get('tipo') == 'Entrada')
            total_saidas = sum(float(x.get('valor_plan', 0)) for x in filtrados if x.get('tipo') == 'Saída')
            
            num_limpo = "".join(filter(str.isdigit, str(celular)))
            if not num_limpo.startswith("55") and len(num_limpo) >= 10:
                num_limpo = f"55{num_limpo}"

            link_direto = f"{APP_URL_BASE}/?nav=conciliacao"

            mensagem = (
                f"🐋 *ORCAS - Conciliação Diária*\n\n"
                f"Olá! Identificamos movimentações pendentes para o dia de hoje que precisam da sua validação.\n\n"
                f"📊 *Resumo do Dia:*\n"
                f"📥 Entradas Previstas: R$ {total_entradas:,.2f}\n"
                f"📤 Saídas Previstas: R$ {total_saidas:,.2f}\n"
                f"📋 Total de Itens: {len(filtrados)}\n\n"
                f"Para confirmar, lançar parciais ou ajustar valores agora mesmo, acesse o painel pelo link abaixo:\n"
                f"🔗 {link_direto}\n\n"
                f"_Tenha um excelente dia de controle financeiro!_"
            )

            endpoint = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
            headers = {
                "Content-Type": "application/json",
                "apikey": EVOLUTION_API_KEY
            }
            payload = {
                "number": num_limpo,
                "options": {
                    "delay": 1200,
                    "presence": "composing"
                },
                "textMessage": {
                    "text": mensagem
                }
            }

            try:
                with httpx.Client(timeout=15.0) as client:
                    response = client.post(endpoint, json=payload, headers=headers)
                    if response.status_code in [200, 201]:
                        print(f" -> Notificação enviada com sucesso para {email} ({num_limpo})")
                    else:
                        print(f" -> Falha no envio para {email}: {response.text}")
            except Exception as e:
                print(f" -> Erro de rede na comunicação com a Evolution API para {email}: {e}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fim do processamento.")


# ==============================================================================
# NOVA FUNÇÃO: GATILHO ACIONADO PELO BATCH01 (ENVIO DO ARQUIVO PDF)
# ==============================================================================
def enviar_zap_orcas(numero, caminho_arquivo, mensagem):
    """
    Ponto de entrada chamado condicionalmente pelo script 'orcas_v01_batch01_3am.py'
    para despachar o PDF gerado na madrugada.
    """
    try:
        import streamlit as st
        EVOLUTION_API_URL = st.secrets.get("EVOLUTION_API_URL", "http://localhost:8080")
        EVOLUTION_API_KEY = st.secrets.get("EVOLUTION_API_KEY", "SUA_API_KEY_AQUI")
        EVOLUTION_INSTANCE = st.secrets.get("EVOLUTION_INSTANCE", "orcas_instance")
    except Exception:
        EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
        EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "SUA_API_KEY_AQUI")
        EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "orcas_instance")

    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY:
        print("Aviso: Variáveis de ambiente da Evolution API não configuradas para envio do PDF.")
        return

    try:
        if not os.path.exists(caminho_arquivo):
            print(f"Erro: O arquivo {caminho_arquivo} não foi localizado para envio.")
            return

        # Formatação do número para padrão internacional exigido pela Evolution API
        num_limpo = "".join(filter(str.isdigit, str(numero)))
        if not num_limpo.startswith("55") and len(num_limpo) >= 10:
            num_limpo = f"55{num_limpo}"

        with open(caminho_arquivo, "rb") as f:
            base64_file = base64.b64encode(f.read()).decode('utf-8')

        endpoint = f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}"
        headers = {
            "Content-Type": "application/json",
            "apikey": EVOLUTION_API_KEY
        }
        payload = {
            "number": num_limpo,
            "mediatype": "document",
            "mimetype": "application/pdf",
            "caption": mensagem,
            "media": base64_file,
            "fileName": os.path.basename(caminho_arquivo)
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(endpoint, json=payload, headers=headers)
            if response.status_code in [200, 201]:
                print(f" -> PDF do resumo diário enviado via WhatsApp para o número {num_limpo}")
            else:
                print(f" -> Falha ao enviar PDF via Evolution API: {response.text}")

    except Exception as e:
        print(f" -> Erro interno ao processar envio do PDF de WhatsApp: {e}")


if __name__ == "__main__":
    executar_envio_diario()