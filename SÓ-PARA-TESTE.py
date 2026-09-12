import json
import re
import time
import zoneinfo
from datetime import datetime, timedelta
from groq import Groq
import pandas as pd
import streamlit as st

# CONSUMO DIRETO DO MOTOR DE CONCILIAÇÃO UNIFICADO
from orcas_v01_conciliacao import (
    buscar_cartoes_lcp,
    salvar_lancamento_oficial,
)

# IMPORTAÇÃO DO MOTOR DE PROJEÇÃO UNIFICADO
from orcas_v01_projetar import executar_inclusao_projetar

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
    1. "descricao": Nome limpo do item (ex: "Mercado", "Curso de Inglês"). Remova verbos ("comprei", "agende"), marcas não essenciais e artigos.
    2. "complemento": Texto de complemento ou numeração de parcela citado (ex: "01 de 12", "Turma A"). Se não citado, null.
    3. "valor": Valor numérico total em float. Ex: "444,00" -> 444.00.
    4. "cartao": Extraia EXATAMENTE o nome do cartão de crédito citado (ex: "MASTER", "Nubank"). Se não citado, null.
    5. "parcelas": Quantidade de parcelas como inteiro. Considerar "3x", "3 vezes" e "3 meses" como 3. Padrão: 1.
    6. "intencao": "PROJETAR" se for lançamento futuro/recorrente/agendado (ex: "planeje", "projete", "mensalmente", "todo dia X"). Caso contrário, "REALIZAR".
    7. "tipo": "Saída" para compras/gastos e "Entrada" para receitas.
    8. "dia_mes": Se for agendamento futuro em dia do mês, informe o número como string (ex: "25"). Se não houver, null.
    9. "dia_semana": Se citar dia da semana ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"). Se não, null.
    10. "regra_fds": Se citar final de semana: "Posterga", "Antecipa" ou "Manter" (padrão).
    11. "is_cartao": true se citar cartão de crédito para a projeção, caso contrário false.
    12. "dia_corte": Dia do mês em inteiro para o corte da fatura do cartão (padrão: 31).
    13. "permite_parcial": true se citar lançamento/realização parcial, caso contrário false.

    Retorne exatamente esta estrutura JSON:
    {{
      "descricao": "Curso de Inglês",
      "complemento": "01 de 12",
      "valor": 350.00,
      "cartao": null,
      "parcelas": 1,
      "intencao": "PROJETAR",
      "tipo": "Saída",
      "dia_mes": "10",
      "dia_semana": null,
      "regra_fds": "Posterga",
      "is_cartao": false,
      "dia_corte": 31,
      "permite_parcial": false
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
        "complemento": None,
        "valor": 0.0,
        "tipo": "Saída",
        "data_compra": str(hoje),
        "permite_parcial": False,
        "cartao": None,
        "parcelas": 1,
        "dia_mes": "",
        "dia_semana": "",
        "regra_fds": "Manter",
        "is_cartao": False,
        "dia_corte": 31,
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
        "complemento": dados_parsed.get("complemento"),
        "valor": valor_float,
        "tipo": dados_parsed.get("tipo", "Saída"),
        "data_compra": str(hoje),
        "permite_parcial": bool(dados_parsed.get("permite_parcial", False)),
        "cartao": cartao_extraido,
        "parcelas": int(dados_parsed.get("parcelas") or 1),
        "dia_mes": str(dados_parsed.get("dia_mes") or ""),
        "dia_semana": str(dados_parsed.get("dia_semana") or ""),
        "regra_fds": str(dados_parsed.get("regra_fds") or "Manter"),
        "is_cartao": bool(dados_parsed.get("is_cartao", False)),
        "dia_corte": int(dados_parsed.get("dia_corte") or 31),
        "erro": None,
    }

  except Exception as e:
    return {
        "transcricao": texto_transcrito,
        "intencao": "REALIZAR",
        "projeto_id": plano_ativo,
        "descricao": "Erro ao Interpretar",
        "complemento": None,
        "valor": 0.0,
        "tipo": "Saída",
        "data_compra": str(hoje),
        "permite_parcial": False,
        "cartao": None,
        "parcelas": 1,
        "dia_mes": "",
        "dia_semana": "",
        "regra_fds": "Manter",
        "is_cartao": False,
        "dia_corte": 31,
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
        complemento = st.text_input(
            "Complemento (Opcional)",
            value=dados.get("complemento") or "",
            placeholder="Ex: 01 de 12",
        )

      with c2:
        valor = st.number_input(
            "Valor Total (R$)",
            value=float(dados.get("valor") or 0.0),
            format="%.2f",
        )
        tipo = st.selectbox(
            "Tipo",
            ["Saída", "Entrada"],
            index=0 if dados.get("tipo") == "Saída" else 1,
        )

        # SE REALIZAR/CONCILIAÇÃO: MANTÉM DADOS DE COMPRA E PARCELAS
        if intencao != "PROJETAR":
          dt_compra = st.date_input(
              "Data da Compra",
              value=datetime.strptime(
                  dados.get("data_compra", str(obter_hoje_brasil())),
                  "%Y-%m-%d",
              ).date(),
              format="DD/MM/YYYY",
          )
          parcelas = st.number_input(
              "Parcelas", value=int(dados.get("parcelas") or 1), min_value=1
          )

          cartao_sel = st.selectbox(
              "Cartão de Crédito", opcoes_cartoes, index=idx_cartao
          )
          cartao_manual = ""
          if cartao_sel == "+ Outro Cartão...":
            cartao_manual = st.text_input(
                "Nome do Cartão", placeholder="Ex: MEU CARTÃO PERSONALIZADO"
            )

      # --- BLOCO EXCLUSIVO QUANDO A INTENÇÃO FOR PROJETAR ---
      if intencao == "PROJETAR":
        st.markdown("---")
        st.markdown("##### 📅 Configurações do Projetar")

        col_rec1, col_rec2, col_rec3 = st.columns(3)
        d_m = col_rec1.text_input(
            "Dia (1-31, DD/MM ou *)", value=str(dados.get("dia_mes") or "")
        )
        
        lista_ds = [
            "",
            "Segunda",
            "Terça",
            "Quarta",
            "Quinta",
            "Sexta",
            "Sábado",
            "Domingo",
        ]
        ds_val = dados.get("dia_semana") or ""
        idx_ds = lista_ds.index(ds_val) if ds_val in lista_ds else 0
        d_s = col_rec2.selectbox("Dia da Semana", lista_ds, index=idx_ds)

        lista_fds = ["Manter", "Antecipa", "Posterga"]
        fds_val = dados.get("regra_fds") or "Manter"
        idx_fds = lista_fds.index(fds_val) if fds_val in lista_fds else 0
        fds = col_rec3.selectbox("Fim de Semana", lista_fds, index=idx_fds)

        col_dt1, col_dt2, col_noc = st.columns(3)
        hoje_br = obter_hoje_brasil()
        inicio_padrao = hoje_br.replace(day=1)

        dt_inicio = col_dt1.date_input(
            "Início", value=inicio_padrao, format="DD/MM/YYYY"
        )
        dt_fim = col_dt2.date_input(
            "Até",
            value=hoje_br.replace(year=hoje_br.year + 1),
            format="DD/MM/YYYY",
        )
        n_ocorrencias = col_noc.number_input(
            "Nº Ocorrências (0 = usar Data Até)",
            min_value=0,
            value=int(dados.get("parcelas") or 0),
        )

        st.markdown("##### 💳 Cartão & Opções Avançadas")
        col_c1, col_c2, col_c3 = st.columns([2, 3, 3])
        is_cartao = col_c1.checkbox(
            "Cartão de Crédito?", value=bool(dados.get("is_cartao", False))
        )
        dia_corte = col_c2.number_input(
            "Dia de Corte Fatura",
            min_value=1,
            max_value=31,
            value=int(dados.get("dia_corte") or 31),
            disabled=not is_cartao,
        )
        chk_parcial = col_c3.checkbox(
            "Permite Lançamento Parcial?",
            value=bool(dados.get("permite_parcial", False)),
        )
      else:
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
        if intencao == "PROJETAR":
          # EXECUÇÃO ATRAVÉS DO MOTOR UNIFICADO DO PROJETAR
          sucesso, msg, qtd = executar_inclusao_projetar(
              supabase=supabase,
              projeto_id=plano_ativo,
              usuario_id=id_usuario,
              descricao=descricao,
              complemento_texto=complemento,
              valor_float=valor,
              tipo=tipo,
              dia_mes=d_m,
              dia_semana=d_s,
              dia_especifico=None,
              n_ocorrencias=n_ocorrencias,
              regra_fds=fds,
              dt_inicio=dt_inicio,
              dt_fim=dt_fim,
              is_cartao=is_cartao,
              dia_corte=dia_corte,
              permitir_parcial=chk_parcial,
          )
          if sucesso:
            st.success(msg)
          else:
            st.error(msg)
        else:
          # EXECUÇÃO DO FLUXO NORMAL DE REALIZAR / CONCILIAÇÃO
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

          str_dt_compra = dt_compra.strftime("%Y-%m-%d")

          # Se houver complemento digitado, anexa à descrição
          desc_completa = (
              f"{descricao} {complemento}".strip() if complemento else descricao
          )

          dados_finais = {
              "intencao": intencao,
              "projeto_id": plano_ativo,
              "descricao": desc_completa,
              "valor": valor,
              "tipo": tipo,
              "data_compra": str_dt_compra,
              "data_movimento": str_dt_compra,
              "data_vencimento": str_dt_compra,
              "cartao": nome_cartao_final,
              "parcelas": parcelas,
              "id_existente": id_final,
              "permite_parcial": permite_parcial_final,
          }
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