from datetime import datetime
import json
import re
import time
import zoneinfo
from groq import Groq
import pandas as pd
import streamlit as st

from orcas_v01_conciliacao import (
    atualizar_valor_plan_cartao,
    buscar_dados_cartao,
    calcular_vencimento_fatura,
    somar_meses_data,
)

LIMITES_USO = {"PADRÃO": 30, "INTERMEDIÁRIO": 100, "ILIMITADO": 999999}


def obter_hoje_brasil():
  return datetime.now(zoneinfo.ZoneInfo("America/Sao_Paulo")).date()


def formatar_moeda_br(valor):
  try:
    return (
        f"R$ {float(valor or 0.0):,.2f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )
  except Exception:
    return "R$ 0,00"


def normalizar_valor_moeda(valor_str):
  """Converte formatos pt-BR de números (ex: '5.880', '5.880,00', '5880,00', '99,35') para float correto."""
  if not valor_str:
    return 0.0

  if isinstance(valor_str, (int, float)):
    return float(valor_str)

  s = str(valor_str).strip().replace("R$", "").strip()

  # Se tem ponto e vírgula (ex: 5.880,00)
  if "." in s and "," in s:
    s = s.replace(".", "").replace(",", ".")
  # Se tem vírgula como decimal (ex: 99,35 ou 5880,00)
  elif "," in s:
    s = s.replace(",", ".")
  # Se tem ponto (ex: 5.880 ou 5.88)
  elif "." in s:
    partes = s.split(".")
    # Se a parte após o ponto tiver 3 dígitos, é ponto de milhar! Ex: 5.880 -> 5880
    if len(partes[-1]) == 3:
      s = "".join(partes)
    # Se tiver 2 dígitos, é decimal americano! Ex: 5.88 -> 5.88

  try:
    return float(s)
  except ValueError:
    return 0.0


def processar_texto_groq(
    client_groq, texto_transcrito, planos_disponiveis, plano_ativo
):
  hoje = obter_hoje_brasil()

  system_prompt = (
      "Você é o assistente financeiro do software ORCAS. "
      "Sua missão é interpretar o comando de áudio do usuário e retornar EXCLUSIVAMENTE "
      "um objeto JSON válido preenchido com extrema precisão."
  )

  user_prompt = f"""
    CONTEXTO DO SISTEMA:
    - Data Atual: {hoje.strftime('%Y-%m-%d')}
    - Projeto Ativo: "{plano_ativo}"
    - Áudio do Usuário: "{texto_transcrito}"

    REGRAS DE INTERPRETAÇÃO E EXTRAÇÃO:
    1. "descricao": O nome limpo do produto/serviço. Remova verbos de compra ("Comprei", "Paguei"), artigos ("o", "a", "um"), e todo o trecho sobre valores ou formas de pagamento.
       - Exemplo: "Comprei o terno Armani por R$ 5.880 e paguei no cartão Visa em 3x" -> "Terno Armani"
       - Exemplo: "Paguei a conta de luz 180" -> "Conta de luz"

    2. "valor": O valor numérico total em formato float (PONTO como separador decimal).
       - ATENÇÃO A PONTOS DE MILHAR BRASILEIROS: "5.880" ou "5.880,00" SIGNIFICA 5880.0 (cinco mil oitocentos e oitenta).
       - Exemplo: "R$ 5.880" -> 5880.0
       - Exemplo: "99,35" -> 99.35

    3. "cartao": Extraia o nome do cartão de crédito mencionado (ex: "Visa", "Mastercard", "Nubank", "Itaucard"). Se nenhum cartão for falado, retorne null.

    4. "parcelas": Quantidade de parcelas como número inteiro.
       - Exemplo: "em três vezes", "em 3x", "parcelado em 3 vezes" -> 3. Se não mencionar parcelamento, retorne 1.

    5. "intencao": "REALIZAR" (se a compra/pagamento já ocorreu ou foi feita no cartão) ou "PROJETAR" (para lançamentos futuros).

    FORMATO EXATO DA SAÍDA JSON:
    {{
      "transcricao": "{texto_transcrito}",
      "intencao": "REALIZAR",
      "projeto_id": "{plano_ativo}",
      "descricao": "Nome limpo do produto",
      "valor": 5880.00,
      "tipo": "Saída",
      "data_vencimento": "{hoje.strftime('%Y-%m-%d')}",
      "permite_parcial": false,
      "cartao": "Visa" ou null,
      "parcelas": 1
    }}
  """

  try:
    res = client_groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    conteudo = res.choices[0].message.content.strip()
    dados_parsed = json.loads(conteudo)

    if isinstance(dados_parsed, dict):
      # Garante a formatação numérica adequada para o Python
      dados_parsed["valor"] = normalizar_valor_moeda(dados_parsed.get("valor"))

      # Limpeza de garantia de pontuação final da descrição
      if dados_parsed.get("descricao"):
        desc = dados_parsed["descricao"].strip()
        desc = re.sub(r"[.,;!?]+$", "", desc).strip()
        dados_parsed["descricao"] = desc.capitalize()

      return dados_parsed
  except Exception as e:
    print(f"Erro no processamento LLM: {e}")

  # Fallback básico em caso de falha de comunicação com a API
  return {
      "transcricao": texto_transcrito,
      "intencao": "REALIZAR",
      "projeto_id": plano_ativo,
      "descricao": "Novo Lançamento",
      "valor": 0.0,
      "tipo": "Saída",
      "data_vencimento": str(hoje),
      "permite_parcial": False,
      "cartao": None,
      "parcelas": 1,
  }


def verificar_limite_uso(supabase, usuario_id):
  try:
    res = (
        supabase.table("usuarios")
        .select("plano_ia, uso_voz_mes")
        .eq("id", str(usuario_id))
        .execute()
    )
    if res and res.data:
      dados = res.data[0]
      plano = str(dados.get("plano_ia") or "PADRAO").upper()
      uso = int(dados.get("uso_voz_mes") or 0)
      limite = LIMITES_USO.get(plano, 30)
      return uso < limite, uso, limite
  except Exception:
    pass
  return True, 0, 30


def incrementar_uso_voz(supabase, usuario_id, uso_atual):
  try:
    supabase.table("usuarios").update({"uso_voz_mes": uso_atual + 1}).eq(
        "id", str(usuario_id)
    ).execute()
  except Exception as e:
    print(f"Aviso Supabase (uso_voz_mes): {e}")


def transcrever_audio_groq(client_groq, audio_bytes):
  return client_groq.audio.transcriptions.create(
      file=("audio.wav", audio_bytes),
      model="whisper-large-v3-turbo",
      language="pt",
      response_format="text",
  ).strip()


def buscar_lancamento_no_banco(supabase, usuario_id, projeto_id, descricao):
  if (
      not descricao
      or not isinstance(descricao, str)
      or len(descricao.strip()) < 3
  ):
    return None
  try:
    res = (
        supabase.table("lancamentos")
        .select("*")
        .eq("usuario_id", str(usuario_id))
        .eq("projeto_id", str(projeto_id))
        .ilike("descricao", f"%{descricao.strip()}%")
        .execute()
    )
    if res and res.data:
      return res.data[0]
  except Exception as e:
    print(f"Erro na busca: {e}")
  return None


def executar_acao_integrada(supabase, usuario_id, dados):
  if not isinstance(dados, dict):
    return "❌ Erro nos dados do lançamento."

  hoje = obter_hoje_brasil()
  projeto_id = str(dados.get("projeto_id"))
  descricao = dados.get("descricao")
  valor = float(dados.get("valor") or 0.0)
  tipo = dados.get("tipo", "Saída")
  dt_venc = dados.get("data_vencimento") or str(hoje)
  cartao = dados.get("cartao")
  parcelas = int(dados.get("parcelas") or 1)
  intencao = dados.get("intencao")
  id_existente = dados.get("id_existente")

  dt_compra = datetime.strptime(dt_venc, "%Y-%m-%d").date()

  # 1. EXCLUIR
  if intencao == "EXCLUIR" and id_existente:
    supabase.table("lancamentos").delete().eq("id", id_existente).execute()
    return f"🗑️ Lançamento **{descricao}** excluído!"

  # 2. CARTÃO DE CRÉDITO
  if cartao and str(cartao).upper() != "NENHUM":
    corte, venc = buscar_dados_cartao(supabase, pd.DataFrame(), cartao)

    dt_1_venc = calcular_vencimento_fatura(
        dt_compra, dia_corte=corte, dia_vencimento=venc
    )

    if dt_1_venc < hoje:
      dt_1_venc = somar_meses_data(dt_1_venc, 1, dia_vencimento=venc)

    base_val = round(valor / parcelas, 2)
    residuo = round(valor - (base_val * parcelas), 2)

    supabase.table("lancamentos").insert({
        "projeto_id": projeto_id,
        "usuario_id": str(usuario_id),
        "descricao": descricao,
        "data": dt_compra.strftime("%Y-%m-%d"),
        "data_vencimento": dt_compra.strftime("%Y-%m-%d"),
        "tipo": tipo,
        "valor_plan": 0.0,
        "valor_real": 0.0,
        "status": "Planejado",
        "cc_tipo": "LCL",
        "cc_qtd_parcelas": parcelas,
    }).execute()

    for i in range(parcelas):
      v_parc = base_val + (residuo if i == (parcelas - 1) else 0.0)
      dt_venc_p = somar_meses_data(dt_1_venc, i, dia_vencimento=venc)

      supabase.table("lancamentos").insert({
          "projeto_id": projeto_id,
          "usuario_id": str(usuario_id),
          "descricao": cartao,
          "cc_descricao": f"{descricao} ({i+1:02d}/{parcelas:02d})",
          "data": dt_venc_p.strftime("%Y-%m-%d"),
          "data_vencimento": dt_venc_p.strftime("%Y-%m-%d"),
          "cc_data_compra": dt_compra.strftime("%Y-%m-%d"),
          "tipo": "Saída",
          "valor_plan": round(v_parc, 2),
          "valor_real": 0.0,
          "status": "Planejado",
          "cc_tipo": "LCL",
          "cc_qtd_parcelas": 0,
      }).execute()

      atualizar_valor_plan_cartao(
          supabase, pd.DataFrame(), cartao, dt_venc_p, usuario_id
      )

    return f"✅ Compra **{descricao}** registrada no cartão **{cartao}** em {parcelas}x!"

  # 3. SEM CARTÃO
  if intencao == "PARCIAL":
    dt_1_dia = dt_compra.replace(day=1).strftime("%Y-%m-%d")
    supabase.table("lancamentos").insert({
        "projeto_id": projeto_id,
        "usuario_id": str(usuario_id),
        "descricao": descricao,
        "data": dt_1_dia,
        "data_vencimento": dt_1_dia,
        "tipo": tipo,
        "valor_plan": 0.0,
        "valor_real": valor,
        "parcial_real": valor,
        "parcial_data": dt_venc,
        "status": "Realizado",
    }).execute()
    return f"✅ Lançamento parcial de **{formatar_moeda_br(valor)}** gravado!"

  elif id_existente and intencao in ["REALIZAR", "ALTERAR"]:
    supabase.table("lancamentos").update({
        "valor_real": valor if intencao == "REALIZAR" else 0.0,
        "valor_plan": valor if intencao == "ALTERAR" else 0.0,
        "status": "Realizado" if intencao == "REALIZAR" else "Planejado",
        "data_vencimento": dt_venc,
    }).eq("id", id_existente).execute()
    return f"✅ Lançamento **{descricao}** atualizado!"

  else:
    status = "Realizado" if intencao == "REALIZAR" else "Planejado"
    v_plan = valor if status == "Planejado" else 0.0
    v_real = valor if status == "Realizado" else 0.0

    supabase.table("lancamentos").insert({
        "projeto_id": projeto_id,
        "usuario_id": str(usuario_id),
        "descricao": descricao,
        "data": dt_venc,
        "data_vencimento": dt_venc,
        "tipo": tipo,
        "valor_plan": v_plan,
        "valor_real": v_real,
        "status": status,
        "permite_parcial": bool(dados.get("permite_parcial")),
    }).execute()
    return f"✅ Lançamento **{descricao}** ({formatar_moeda_br(valor)}) salvo!"


def fechar_modal_voz():
  """Limpa estados da sessão para fechar o dialog do Streamlit e resetar o gravador."""
  st.session_state.etapa_voz = "gravacao"
  st.session_state.dados_interpretados = None
  st.session_state.hash_ultimo_audio = None
  st.session_state.audio_key = st.session_state.get("audio_key", 0) + 1

  for k in [
      "abrir_modal_voz",
      "exibir_modal_voz",
      "modal_voz_aberto",
      "show_voice_modal",
  ]:
    if k in st.session_state:
      st.session_state[k] = False


@st.dialog("🎙️ Conversar com o ORCAS")
def exibir_modal_voz_orcas(supabase, id_usuario, planos_disponiveis=None):
  if not planos_disponiveis:
    planos_disponiveis = [st.session_state.get("projeto_ativo") or "Padrão"]
  plano_ativo = st.session_state.get("projeto_ativo", planos_disponiveis[0])

  groq_key = st.secrets.get("GROQ_API_KEY")
  if not groq_key:
    st.error("❌ Chave GROQ_API_KEY não configurada nos Secrets!")
    return

  client_groq = Groq(api_key=groq_key.strip())

  if "etapa_voz" not in st.session_state:
    st.session_state.etapa_voz = "gravacao"

  # TELA 1: GRAVAÇÃO
  if st.session_state.etapa_voz == "gravacao":
    pode_usar, uso, limite = verificar_limite_uso(supabase, id_usuario)
    if not pode_usar:
      st.error(f"⚠️ Limite mensal atingido! ({uso}/{limite})")
      return

    st.caption(f"📊 Uso do recurso no mês: **{uso}/{limite}**")
    audio = st.audio_input(
        "Grave seu comando:", key=f"audio_{st.session_state.get('audio_key', 0)}"
    )

    if audio:
      audio_bytes = audio.getvalue()
      if hash(audio_bytes) != st.session_state.get("hash_ultimo_audio"):
        with st.spinner("🤖 ORCAS processando..."):
          incrementar_uso_voz(supabase, id_usuario, uso)
          texto = transcrever_audio_groq(client_groq, audio_bytes)
          dados = processar_texto_groq(
              client_groq, texto, planos_disponiveis, plano_ativo
          )

          st.session_state.hash_ultimo_audio = hash(audio_bytes)

          if isinstance(dados, dict):
            item_banco = buscar_lancamento_no_banco(
                supabase, id_usuario, plano_ativo, dados.get("descricao")
            )
            if item_banco and dados.get("intencao") in [
                "ALTERAR",
                "EXCLUIR",
                "PARCIAL",
            ]:
              dados["id_existente"] = item_banco.get("id")
              if not dados.get("valor") or dados.get("valor") == 0:
                dados["valor"] = float(
                    item_banco.get("valor_plan")
                    or item_banco.get("valor_real")
                    or 0
                )

          st.session_state.dados_interpretados = dados
          st.session_state.etapa_voz = "confirmacao"
          st.rerun()

  # TELA 2: CONFIRMAÇÃO
  elif st.session_state.etapa_voz == "confirmacao":
    dados = st.session_state.dados_interpretados or {}
    st.info(f'🗣️ **Você disse:** "{dados.get("transcricao")}"')

    with st.form("form_confirmacao_voz"):
      c1, c2 = st.columns(2)
      with c1:
        intencao = st.selectbox(
            "Ação",
            ["REALIZAR", "PROJETAR", "PARCIAL", "ALTERAR", "EXCLUIR"],
            index=0 if dados.get("intencao") == "REALIZAR" else 1,
        )
        descricao = st.text_input("Descrição", value=dados.get("descricao", ""))
        cartao = st.text_input(
            "Cartão de Crédito", value=dados.get("cartao") or "Nenhum"
        )
      with c2:
        valor = st.number_input(
            "Valor Total (R$)",
            value=float(dados.get("valor") or 0.0),
            format="%.2f",
        )
        dt_venc = st.date_input(
            "Vencimento",
            value=datetime.strptime(
                dados.get("data_vencimento", str(obter_hoje_brasil())),
                "%Y-%m-%d",
            ).date(),
            format="DD/MM/YYYY",
        )
        parcelas = st.number_input(
            "Parcelas", value=int(dados.get("parcelas") or 1), min_value=1
        )

      b_salvar, b_refazer, b_sair = st.columns(3)
      sub_salvar = b_salvar.form_submit_button(
          "✅ Confirmar", type="primary", use_container_width=True
      )
      sub_refazer = b_refazer.form_submit_button(
          "🔄 Refazer", use_container_width=True
      )
      sub_sair = b_sair.form_submit_button("❌ Sair", use_container_width=True)

      if sub_salvar:
        dados_finais = {
            "intencao": intencao,
            "projeto_id": plano_ativo,
            "descricao": descricao,
            "valor": valor,
            "tipo": dados.get("tipo", "Saída"),
            "data_vencimento": dt_venc.strftime("%Y-%m-%d"),
            "cartao": cartao,
            "parcelas": parcelas,
            "id_existente": dados.get("id_existente"),
            "permite_parcial": dados.get("permite_parcial"),
        }
        st.success(executar_acao_integrada(supabase, id_usuario, dados_finais))
        time.sleep(1)
        fechar_modal_voz()
        st.rerun()

      elif sub_refazer:
        st.session_state.etapa_voz = "gravacao"
        st.session_state.audio_key = st.session_state.get("audio_key", 0) + 1
        st.rerun()

      elif sub_sair:
        fechar_modal_voz()
        st.rerun()