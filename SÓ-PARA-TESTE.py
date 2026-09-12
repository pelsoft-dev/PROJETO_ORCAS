import json
import re
import time
from datetime import datetime, timedelta, timezone

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
  fuso_br = timezone(timedelta(hours=-3))
  return datetime.now(fuso_br).date()


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


def obter_datas_limite_projeto(supabase, projeto_id):
  """Busca as datas oficiais na tabela config_projetos filtrando por projeto_id."""
  hoje_br = obter_hoje_brasil()
  dt_ini_valida = None
  dt_fim_valida = None

  if projeto_id:
    try:
      res = (
          supabase.table("config_projetos")
          .select("data_ini, data_fim")
          .eq("projeto_id", str(projeto_id))
          .execute()
      )

      if not res or not res.data:
        res = (
            supabase.table("config_projetos")
            .select("data_ini, data_fim")
            .ilike("projeto_id", str(projeto_id).strip())
            .execute()
        )

      if res and res.data:
        dados = res.data[0]
        d_ini = dados.get("data_ini")
        d_fim = dados.get("data_fim")

        if d_ini:
          dt_ini_valida = datetime.strptime(str(d_ini)[:10], "%Y-%m-%d").date()
        if d_fim:
          dt_fim_valida = datetime.strptime(str(d_fim)[:10], "%Y-%m-%d").date()

    except Exception as e:
      print(f"Aviso ao buscar limite na config_projetos: {e}")

  val_i_p = hoje_br.replace(day=1)
  if dt_ini_valida and val_i_p < dt_ini_valida:
    val_i_p = dt_ini_valida

  if dt_fim_valida:
    val_f_p = dt_fim_valida
  else:
    val_f_p = datetime(hoje_br.year, 12, 31).date()

  if dt_ini_valida and val_f_p < dt_ini_valida:
    val_f_p = dt_ini_valida

  return val_i_p, val_f_p, dt_ini_valida, dt_fim_valida


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
    Data Atual Hoje: {hoje.strftime('%Y-%m-%d')}
    Projeto Ativo: "{plano_ativo}"

    Regras de extração:
    1. "descricao": Nome limpo do item (ex: "Mercado", "Dívida edinho", "Musculação"). Remova verbos de comando ("planeje", "projete", "pague"), artigos e conectivos.
    2. "complemento": Texto de complemento ou parcelas se explicitado. Se não, null.
    3. "valor": Valor numérico total em float. Ex: "5 mil reais" -> 5000.00, "357,00" -> 357.00.
    4. "cartao": Nome do cartão de crédito se citado (ex: "MASTER"). Se não, null.
    5. "parcelas": Quantidade de parcelas se houver parcelamento explícito. Padrão: 1.
    6. "intencao": "PROJETAR" para planejamento/agendamento de datas futuras/recorrentes. Se for realização imediata/passada, "REALIZAR".
    7. "tipo": "Saída" para compras/gastos e "Entrada" para receitas.
    8. "dia_mes": O dia do mês numérico ou formato DD/MM se for uma data específica. Se for pontual ex "15 de dezembro de 2026", pode colocar "15" ou "15/12".
    9. "data_inicio": Data em formato YYYY-MM-DD para o início do agendamento.
       - Se for uma data ÚNICA/PONTUAL (ex: "para o dia 15 de dezembro de 2026"), data_inicio DEVE SER "2026-12-15".
       - Se for um período (ex: "entre setembro de 2026 até abril de 2027"), data_inicio DEVE SER o primeiro dia desse mês de início: "2026-09-01".
       - Se não for citada data específica, passe null.
    10. "data_fim": Data em formato YYYY-MM-DD para o fim do agendamento.
       - Se for uma data ÚNICA/PONTUAL (ex: "para o dia 15 de dezembro de 2026"), data_fim DEVE SER IGUAL À DATA INÍCIO: "2026-12-15".
       - Se for um período (ex: "entre setembro de 2026 até abril de 2027"), data_fim DEVE SER o último dia desse mês final: "2027-04-30".
       - Se não for citada data final específica, passe null.
    11. "dia_semana": Se citar dia da semana ("Segunda", etc). Se não, null.
    12. "regra_fds": "Posterga", "Antecipa" ou "Manter" (padrão).
    13. "is_cartao": true se citar cartão de crédito para a projeção, caso contrário false.
    14. "dia_corte": Dia do mês em inteiro (padrão: 31).
    15. "permite_parcial": true ou false.

    Retorne exatamente esta estrutura JSON:
    {{
      "descricao": "Dívida edinho",
      "complemento": null,
      "valor": 5000.00,
      "cartao": null,
      "parcelas": 1,
      "intencao": "PROJETAR",
      "tipo": "Saída",
      "dia_mes": "15",
      "data_inicio": "2026-12-15",
      "data_fim": "2026-12-15",
      "dia_semana": null,
      "regra_fds": "Manter",
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
        "data_inicio": None,
        "data_fim": None,
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
        "intencao": dados_parsed.get("intencao", "PROJETAR"),
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
        "data_inicio": dados_parsed.get("data_inicio"),
        "data_fim": dados_parsed.get("data_fim"),
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
        "data_inicio": None,
        "data_fim": None,
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
  st.session_state.abrir_modal_orcas = False
  st.session_state.exibir_modal_voz = False
  st.session_state.etapa_voz = "gravacao"
  st.session_state.dados_interpretados = None
  st.session_state.hash_ultimo_audio = None
  st.session_state.audio_key = st.session_state.get("audio_key", 0) + 1


def buscar_df_lancamentos_projeto(supabase, projeto_id):
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

          st.session_state.dados_interpretados = dados
          st.session_state.etapa_voz = "confirmacao"
          st.rerun()

  # TELA 2: CONFIRMAÇÃO
  elif st.session_state.etapa_voz == "confirmacao":
    dados = st.session_state.dados_interpretados or {}
    st.info(f'🗣️ **Você disse:** "{dados.get("transcricao")}"')

    if dados.get("erro"):
      st.error(f"⚠️ **Detalhe do erro da IA:** `{dados.get('erro')}`")

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

    opcoes_acao = ["PROJETAR", "REALIZAR", "PARCIAL", "ALTERAR", "EXCLUIR"]
    intencao_sugerida = dados.get("intencao", "PROJETAR")
    idx_intencao = (
        opcoes_acao.index(intencao_sugerida)
        if intencao_sugerida in opcoes_acao
        else 0
    )

    intencao_selecionada = st.selectbox(
        "Ação Desejada",
        opcoes_acao,
        index=idx_intencao,
        key="sb_intencao_confirmacao",
    )

    # Limites gerais do plano vindos do banco
    dt_inicio_plano_db, dt_fim_plano_db, min_db, max_db = (
        obter_datas_limite_projeto(supabase, plano_ativo)
    )

    # DEFINIÇÃO DINÂMICA DAS DATAS DO FORMULÁRIO (SUGESTÃO DA IA VS LIMITES DO BANCO)
    val_dt_inicio = dt_inicio_plano_db
    val_dt_fim = dt_fim_plano_db

    if dados.get("data_inicio"):
      try:
        val_dt_inicio = datetime.strptime(
            dados.get("data_inicio"), "%Y-%m-%d"
        ).date()
      except Exception:
        pass

    if dados.get("data_fim"):
      try:
        val_dt_fim = datetime.strptime(
            dados.get("data_fim"), "%Y-%m-%d"
        ).date()
      except Exception:
        pass

    with st.form("form_confirmacao_voz"):
      c1, c2 = st.columns(2)
      with c1:
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

      # DADOS ESPECÍFICOS DE REALIZAR / CONCILIAÇÃO
      if intencao_selecionada != "PROJETAR":
        c_real1, c_real2 = st.columns(2)
        dt_compra = c_real1.date_input(
            "Data da Compra",
            value=datetime.strptime(
                dados.get("data_compra", str(obter_hoje_brasil())), "%Y-%m-%d"
            ).date(),
            format="DD/MM/YYYY",
        )
        parcelas = c_real2.number_input(
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

      # DADOS ESPECÍFICOS DE PROJETAR
      else:
        st.markdown("---")
        st.markdown("##### 📅 Configurações de Recorrência (Projetar)")

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

        dt_inicio = col_dt1.date_input(
            "Início",
            value=val_dt_inicio,
            min_value=min_db,
            max_value=max_db,
            format="DD/MM/YYYY",
        )
        dt_fim = col_dt2.date_input(
            "Até",
            value=val_dt_fim,
            min_value=min_db,
            max_value=max_db,
            format="DD/MM/YYYY",
        )
        n_ocorrencias = col_noc.number_input(
            "Nº Ocorrências (0 = usar Data Até)",
            min_value=0,
            value=int(
                dados.get("parcelas") if dados.get("parcelas") != 1 else 0
            ),
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

      if intencao_selecionada != "PROJETAR":
        is_parcial_intencao = intencao_selecionada == "PARCIAL"
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
        if intencao_selecionada == "PROJETAR":
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
            st.session_state["msg_sucesso"] = msg
          else:
            st.error(msg)
        else:
          id_final = (
              None
              if intencao_selecionada == "PARCIAL"
              else dados.get("id_existente")
          )
          permite_parcial_final = (
              False if intencao_selecionada == "PARCIAL" else chk_parcial
          )
          nome_cartao_final = (
              cartao_manual.strip()
              if cartao_sel == "+ Outro Cartão..."
              else cartao_sel
          )
          str_dt_compra = dt_compra.strftime("%Y-%m-%d")
          desc_completa = (
              f"{descricao} {complemento}".strip() if complemento else descricao
          )

          dados_finais = {
              "intencao": intencao_selecionada,
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
          st.session_state["msg_sucesso"] = msg

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