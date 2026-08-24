import json
import re
import time
import zoneinfo
from datetime import datetime
from groq import Groq
import pandas as pd
import streamlit as st

# CONSUMO DIRETO DO MOTOR DE CONCILIAÇÃO UNIFICADO
from orcas_v01_conciliacao import (
    buscar_cartoes_lcp,
    salvar_lancamento_oficial,
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
  if valor_str is None:
    return 0.0
  if isinstance(valor_str, (int, float)):
    return float(valor_str)

  s = str(valor_str).strip().replace("R$", "").strip()
  if "." in s and "," in s:
    s = s.replace(".", "").replace(",", ".")
  elif "," in s:
    s = s.replace(",", ".")
  elif "." in s:
    partes = s.split(".")
    if len(partes[-1]) == 3:
      s = "".join(partes)

  try:
    return float(s)
  except ValueError:
    return 0.0


def processar_texto_groq(
    client_groq, texto_transcrito, planos_disponiveis, plano_ativo
):
  hoje = obter_hoje_brasil()

  system_prompt = (
      "Você é o assistente financeiro do software ORCAS.\n"
      "Sua tarefa é analisar a frase gravada pelo usuário e responder"
      " EXCLUSIVAMENTE com um objeto JSON válido contendo a estrutura"
      ' solicitada.\nNão inclua explicações ou formatação markdown como ```json.'
  )

  user_prompt = f"""
    Texto Transcrito: "{texto_transcrito}"
    Data Atual: {hoje.strftime('%Y-%m-%d')}
    Projeto Ativo: "{plano_ativo}"

    Regras de extração:
    1. "descricao": Nome limpo do item (ex: "Mercado"). Remova verbos ("comprei"), marcas não essenciais, artigos e preços.
    2. "valor": Valor numérico total em float. Ex: "444,00" -> 444.00.
    3. "cartao": Extraia EXATAMENTE o nome do cartão de crédito citado pelo usuário (ex: "MASTER", "Cartão do Fulano", "Nubank", "VISA"). O usuário pode dar qualquer nome ao cartão dele. Se nenhum for citado, retorne null.
    4. "parcelas": Quantidade de parcelas como inteiro. Considerar "3x", "3 vezes" e "3 meses" como 3. Padrão: 1.
    5. "intencao": "REALIZAR" para compras efetuadas, "PROJETAR" para gastos futuros.
    6. "tipo": "Saída" para compras/gastos e "Entrada" para receitas.

    Retorne exatamente esta estrutura JSON:
    {{
      "descricao": "Mercado",
      "valor": 444.00,
      "cartao": "MASTER",
      "parcelas": 3,
      "intencao": "REALIZAR",
      "tipo": "Saída"
    }}
  """

  modelos_candidatos = [
      "openai/gpt-oss-20b",
      "llama-3.3-70b-versatile",
      "meta-llama/llama-4-scout-17b-16e-instruct",
      "llama-3.1-8b-instant",
  ]

  res = None
  ultimo_erro = None

  for modelo in modelos_candidatos:
    try:
      res = client_groq.chat.completions.create(
          model=modelo,
          messages=[
              {"role": "system", "content": system_prompt},
              {"role": "user", "content": user_prompt},
          ],
          temperature=0.0,
          response_format={"type": "json_object"},
      )
      if res and res.choices:
        break
    except Exception as err:
      ultimo_erro = err
      continue

  if not res or not res.choices:
    return {
        "transcricao": texto_transcrito,
        "intencao": "REALIZAR",
        "projeto_id": plano_ativo,
        "descricao": "Erro de Modelo",
        "valor": 0.0,
        "tipo": "Saída",
        "data_vencimento": str(hoje),
        "permite_parcial": False,
        "cartao": None,
        "parcelas": 1,
        "erro": f"Nenhum modelo Groq respondeu. Último erro: {ultimo_erro}.",
    }

  try:
    conteudo = res.choices[0].message.content.strip()
    conteudo_limpo = re.sub(
        r"^```json\s*|^```\s*|\s*```$", "", conteudo, flags=re.MULTILINE
    ).strip()
    match = re.search(r"\{.*\}", conteudo_limpo, re.DOTALL)
    if match:
      conteudo_limpo = match.group(0)

    dados_parsed = json.loads(conteudo_limpo)

    valor_float = normalizar_valor_moeda(dados_parsed.get("valor"))
    desc = str(dados_parsed.get("descricao") or "Novo Lançamento").strip()
    desc = re.sub(r"[.,;!?]+$", "", desc).strip()

    cartao_extraido = dados_parsed.get("cartao")
    if isinstance(
        cartao_extraido, str
    ) and cartao_extraido.lower() in [
        "none",
        "null",
        "nenhum",
        "",
    ]:
      cartao_extraido = None
    elif isinstance(cartao_extraido, str):
      cartao_extraido = cartao_extraido.strip()

    return {
        "transcricao": texto_transcrito,
        "intencao": dados_parsed.get("intencao", "REALIZAR"),
        "projeto_id": plano_ativo,
        "descricao": desc.capitalize(),
        "valor": valor_float,
        "tipo": dados_parsed.get("tipo", "Saída"),
        "data_vencimento": str(hoje),
        "permite_parcial": False,
        "cartao": cartao_extraido,
        "parcelas": int(dados_parsed.get("parcelas") or 1),
        "erro": None,
    }

  except Exception as e:
    return {
        "transcricao": texto_transcrito,
        "intencao": "REALIZAR",
        "projeto_id": plano_ativo,
        "descricao": "Erro ao Interpretar",
        "valor": 0.0,
        "tipo": "Saída",
        "data_vencimento": str(hoje),
        "permite_parcial": False,
        "cartao": None,
        "parcelas": 1,
        "erro": f"Erro na conversão do JSON: {e}",
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


def fechar_modal_voz():
  """Reseta as flags do modal no session state."""
  st.session_state.abrir_modal_orcas = False
  st.session_state.etapa_voz = "gravacao"
  st.session_state.dados_interpretados = None
  st.session_state.hash_ultimo_audio = None
  st.session_state.audio_key = st.session_state.get("audio_key", 0) + 1


def buscar_df_lancamentos_projeto(supabase, projeto_id):
  """Busca os lançamentos do projeto no banco para extrair cartões ($CCP)."""
  try:
    res = (
        supabase.table("lancamentos")
        .select("*")
        .eq("projeto_id", str(projeto_id))
        .execute()
    )
    if res and res.data:
      return pd.DataFrame(res.data)
  except Exception:
    pass
  return pd.DataFrame()


@st.dialog("🎙️ Conversar com o ORCAS")
def _renderizar_dialogo_voz(supabase, id_usuario, planos_disponiveis):
  plano_ativo = st.session_state.get("projeto_ativo", planos_disponiveis[0])

  groq_key = st.secrets.get("GROQ_API_KEY")
  if not groq_key:
    st.error("❌ Chave GROQ_API_KEY não configurada nos Secrets!")
    return

  client_groq = Groq(api_key=groq_key.strip())

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
            if item_banco:
              is_pai_parcial = bool(
                  item_banco.get("permite_parcial")
              ) or bool(item_banco.get("parcial_real"))

              if is_pai_parcial:
                dados["intencao"] = "PARCIAL"
                dados["permite_parcial"] = False
                # IMPORTANTE: NÃO vincular o id_existente para não editar/sobrescrever o PAI
                dados["id_existente"] = None
              else:
                dados["id_existente"] = item_banco.get("id")
                dados["permite_parcial"] = bool(
                    item_banco.get("permite_parcial")
                )

              if dados.get("intencao") in ["ALTERAR", "EXCLUIR"]:
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

    if dados.get("erro"):
      st.error(f"⚠️ **Detalhe do erro da IA:** `{dados.get('erro')}`")

    # BUSCA OPÇÕES DE CARTÕES DISPONÍVEIS NO PLANO ATIVO
    df_proj = buscar_df_lancamentos_projeto(supabase, plano_ativo)
    opcoes_cartoes = buscar_cartoes_lcp(df_proj)

    # CORRESPONDÊNCIA / MONTAGEM DA LISTA
    cartao_detectado = dados.get("cartao")
    if cartao_detectado:
      cartao_clean = str(cartao_detectado).strip()
      match_opt = next(
          (opt for opt in opcoes_cartoes if opt.upper() == cartao_clean.upper()),
          None,
      )

      if match_opt:
        idx_cartao = opcoes_cartoes.index(match_opt)
      else:
        # Se for um nome personalizado de cartão não cadastrado ainda, insere no dropdown antes de "+ Outro Cartão..."
        opcoes_cartoes.insert(-1, cartao_clean)
        idx_cartao = opcoes_cartoes.index(cartao_clean)
    else:
      idx_cartao = 0

    with st.form("form_confirmacao_voz"):
      c1, c2 = st.columns(2)
      with c1:
        opcoes_acao = ["REALIZAR", "PROJETAR", "PARCIAL", "ALTERAR", "EXCLUIR"]
        intencao_atual = dados.get("intencao", "REALIZAR")
        idx_intencao = (
            opcoes_acao.index(intencao_atual)
            if intencao_atual in opcoes_acao
            else 0
        )

        intencao = st.selectbox("Ação", opcoes_acao, index=idx_intencao)
        descricao = st.text_input("Descrição", value=dados.get("descricao", ""))
        cartao_sel = st.selectbox(
            "Cartão de Crédito", opcoes_cartoes, index=idx_cartao
        )

        cartao_manual = ""
        if cartao_sel == "+ Outro Cartão...":
          cartao_manual = st.text_input(
              "Nome do Cartão", placeholder="Ex: MEU CARTÃO PERSONALIZADO"
          )

      with c2:
        valor = st.number_input(
            "Valor Total (R$)",
            value=float(dados.get("valor") or 0.0),
            format="%.2f",
        )
        dt_venc = st.date_input(
            "Data da Compra",
            value=datetime.strptime(
                dados.get("data_vencimento", str(obter_hoje_brasil())),
                "%Y-%m-%d",
            ).date(),
            format="DD/MM/YYYY",
        )
        parcelas = st.number_input(
            "Parcelas", value=int(dados.get("parcelas") or 1), min_value=1
        )

      # Se for PARCIAL, força False no checkbox e desabilita a edição da flag
      is_parcial_intencao = intencao == "PARCIAL"
      val_parcial_chk = (
          False
          if is_parcial_intencao
          else bool(dados.get("permite_parcial", False))
      )

      chk_parcial = st.checkbox(
          "Permite Lançamento Parcial",
          value=val_parcial_chk,
          disabled=is_parcial_intencao,
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
        id_final = (
            None if intencao == "PARCIAL" else dados.get("id_existente")
        )
        permite_parcial_final = (
            False if intencao == "PARCIAL" else chk_parcial
        )

        nome_cartao_final = (
            cartao_manual.strip()
            if cartao_sel == "+ Outro Cartão..."
            else cartao_sel
        )

        dados_finais = {
            "intencao": intencao,
            "projeto_id": plano_ativo,
            "descricao": descricao,
            "valor": valor,
            "tipo": dados.get("tipo", "Saída"),
            "data_vencimento": dt_venc.strftime("%Y-%m-%d"),
            "cartao": nome_cartao_final,
            "parcelas": parcelas,
            "id_existente": id_final,
            "permite_parcial": permite_parcial_final,
        }
        # CHAMADA OFICIAL AO MOTOR DE CONCILIAÇÃO
        msg = salvar_lancamento_oficial(supabase, id_usuario, dados_finais)
        st.success(msg)
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


def exibir_modal_voz_orcas(supabase, id_usuario, planos_disponiveis=None):
  if "etapa_voz" not in st.session_state or not st.session_state.etapa_voz:
    st.session_state.etapa_voz = "gravacao"

  if not planos_disponiveis:
    planos_disponiveis = [st.session_state.get("projeto_ativo") or "Padrão"]

  _renderizar_dialogo_voz(supabase, id_usuario, planos_disponiveis)