from datetime import date, datetime, timedelta
import json
import re
import time
import unicodedata
import zoneinfo
from groq import Groq
import streamlit as st

# Limites mensais de uso do recurso por voz
LIMITES_USO = {
    "PADRÃO": 30,
    "INTERMEDIÁRIO": 100,
    "ILIMITADO": 999999,
}

# Palavras de preenchimento a serem ignoradas na busca de lançamentos
STOPWORDS_FINANCEIRAS = {
    "CONTA",
    "CONTAS",
    "LANCAMENTO",
    "LANCAMENTOS",
    "BOLETO",
    "BOLETOS",
    "FATURA",
    "FATURAS",
    "PAGAMENTO",
    "PAGAMENTOS",
    "PARCELA",
    "PARCELAS",
    "DE",
    "DO",
    "DA",
    "DOS",
    "DAS",
    "E",
    "A",
    "O",
}


def obter_hoje_brasil():
  """Garante que a data de HOJE respeite sempre o fuso horário de Brasília (GMT-3)."""
  fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
  return datetime.now(fuso_br).date()


def normalizar_texto(texto):
  """Remove acentos, pontos, traços e converte para maiúsculo para comparação precisa."""
  if not texto:
    return ""
  nfkd = unicodedata.normalize("NFKD", str(texto))
  texto_sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
  texto_limpo = re.sub(r"[^a-zA-Z0-9\s]", " ", texto_sem_acento)
  return " ".join(texto_limpo.split()).upper()


def limpar_descricao_busca(descricao):
  """Remove palavras como 'conta', 'lançamento', 'fatura' para facilitar o match no banco."""
  norma = normalizar_texto(descricao)
  palavras = [p for p in norma.split() if p not in STOPWORDS_FINANCEIRAS]
  return " ".join(palavras) if palavras else norma


def buscar_planos_do_usuario(supabase, usuario_id):
  """Busca no Supabase todos os planos/projetos vinculados ao usuário."""
  try:
    res = (
        supabase.table("lancamentos")
        .select("projeto_id")
        .eq("usuario_id", str(usuario_id))
        .execute()
    )
    if res and res.data:
      planos = sorted(
          list({
              str(item["projeto_id"])
              for item in res.data
              if item.get("projeto_id")
          })
      )
      if planos:
        return planos
  except Exception as e:
    print(f"Erro ao buscar planos do usuário: {e}")
  return ["Padrão"]


def verificar_limite_uso(supabase, usuario_id):
  """Verifica no Supabase se o usuário ainda possui cota de uso de voz no mês."""
  try:
    res = (
        supabase.table("usuarios")
        .select("*")
        .eq("id", usuario_id)
        .execute()
    )

    if res and hasattr(res, "data") and len(res.data) > 0:
      dados_user = res.data[0]
      plano_ia = str(dados_user.get("plano_ia") or "PADRAO").upper()
      uso_atual = int(dados_user.get("uso_voz_mes") or 0)
      limite_permitido = LIMITES_USO.get(plano_ia, 30)

      return uso_atual < limite_permitido, uso_atual, limite_permitido
  except Exception:
    pass
  return True, 0, 30


def incrementar_uso_voz(supabase, usuario_id, uso_atual):
  """Incrementa a contagem de uso após o áudio ser processado com sucesso."""
  try:
    supabase.table("usuarios").update({"uso_voz_mes": uso_atual + 1}).eq(
        "id", usuario_id
    ).execute()
  except Exception as e:
    print(f"Erro ao incrementar limite: {e}")


def transcrever_audio_groq(client_groq, audio_bytes):
  """Transcreve o áudio gravado usando o modelo Whisper no Groq."""
  transcription = client_groq.audio.transcriptions.create(
      file=("audio.wav", audio_bytes),
      model="whisper-large-v3-turbo",
      language="pt",
      response_format="text",
  )
  return transcription.strip()


def processar_texto_groq(
    client_groq, texto_transcrito, planos_disponiveis, plano_ativo=None
):
  """Processa o texto no Groq (Llama 3.3) para gerar a estrutura JSON."""
  plano_referencia = (
      plano_ativo
      if plano_ativo
      else (planos_disponiveis[0] if planos_disponiveis else "Padrão")
  )

  # AJUSTE DE FUSO HORÁRIO BRASÍLIA (GMT-3)
  hoje_dt = obter_hoje_brasil()
  amanha_dt = hoje_dt + timedelta(days=1)
  ontem_dt = hoje_dt - timedelta(days=1)

  prompt = f"""
    Você é o assistente financeiro inteligente do aplicativo ORCAS.
    
    INFORMAÇÕES DE CONTEXTO TEMPORAL RIGOROSAS (FUSO HORÁRIO BRASÍLIA):
    - Data de HOJE: {hoje_dt.strftime('%Y-%m-%d')} ({hoje_dt.strftime('%A')})
    - Data de AMANHÃ: {amanha_dt.strftime('%Y-%m-%d')}
    - Data de ONTEM: {ontem_dt.strftime('%Y-%m-%d')}
    
    CONTEXTO DE PLANOS:
    - Plano ATUALMENTE SELECIONADO: "{plano_referencia}"
    - Todos os planos disponíveis: {planos_disponiveis}

    ÁUDIO DO USUÁRIO: "{texto_transcrito}"

    REGRAS RÍGIDAS DE INTERPRETAÇÃO:
    1. INTENÇÃO:
       - "PROJETAR": Criar/incluir um novo lançamento futuro, agendamento ou conta a pagar/receber (ex: "planejar para dia X", "projetar gasto", "agendar para dia X").
       - "REALIZAR": Baixar, pagar ou liquidar uma conta existente ou lançamento do dia.
       - "PARCIAL": Quando for um gasto do dia a dia (ex: Supermercado, Combustível, Farmácia, Restaurante) que abate/entra como lançamento parcial de uma projeção orçada.
       - "ALTERAR": Modificar valor, nome, descrição ou data de uma conta existente.
       - "EXCLUIR": APENAS quando o usuário usar termos explícitos como "deletar", "excluir", "apagar", "remover".
       - "CONSULTAR": Perguntas sobre saldos, totais ou resumos.

    2. PERMITE PARCIAIS E RECORRÊNCIA TEMPORAL (permite_parcial):
       - Identifique se o usuário mencionou permitir parciais (ex: "permita parciais", "permita parcial", "aceita parcial", "com parcial"). Se sim, defina permite_parcial = true.
       - Se o usuário disse "em todos os meses do meu plano" ou "em todos os meses", defina recorrencia_tipo = "TODOS".
       - Se o usuário especificou um intervalo de meses (ex: "de agosto até dezembro de 2026", "de maio a outubro"), defina recorrencia_tipo = "PERIODO", e preencha mes_inicio e mes_fim no formato YYYY-MM-01 (ex: "2026-08-01" e "2026-12-01").
       - Quando permite_parcial for true, a data base do lançamento DEVE ser o dia 01 do mês correspondente (ex: YYYY-MM-01).

    3. DATA DE VENCIMENTO OU DA OCORRÊNCIA (data_vencimento):
       - PRIORIDADE MÁXIMA: Se o usuário mencionou uma data específica (ex: "dia 20 de agosto de 2026", "20/08/2026", "na data 30/07/2026", "no dia 15 de maio"), você DEVE obrigatoriamente converter e atribuir essa data no formato YYYY-MM-DD. NUNCA substitua pela data de hoje nem por datas passadas se o usuário citou uma data explícita.
       - Se o usuário solicitar "permita parciais", garanta que a data seja dia 01 do mês citado ou do mês atual (ex: YYYY-MM-01).
       - Se o usuário disse "amanhã", atribua OBRIGATORIAMENTE a data: "{amanha_dt.strftime('%Y-%m-%d')}".
       - Se o usuário disse "hoje" ou "na data de hoje", atribua OBRIGATORIAMENTE a data: "{hoje_dt.strftime('%Y-%m-%d')}".
       - Se o usuário disse "ontem", atribua OBRIGATORIAMENTE a data: "{ontem_dt.strftime('%Y-%m-%d')}".
       - Se nenhuma data foi mencionada para inclusão/projeção/realização, use a data de HOJE: "{hoje_dt.strftime('%Y-%m-%d')}".

    4. MÊS DE REFERÊNCIA (mes_referencia):
       - Se o usuário mencionou um mês específico (ex: "em julho", "de setembro"), retorne o mês numérico (1 a 12). Caso contrário, retorne o mês da data_vencimento identificada.

    5. DESCRIÇÃO:
       - Extraia apenas o identificador/nome da conta ou serviço.
       - Remova termos genéricos iniciais como "conta", "lançamento", "boleto", "fatura".

    Responda EXCLUSIVAMENTE um objeto JSON válido no formato:
    {{
      "transcricao": "{texto_transcrito}",
      "intencao": "PROJETAR" | "REALIZAR" | "PARCIAL" | "ALTERAR" | "EXCLUIR" | "CONSULTAR",
      "projeto_id": "Plano citado ou '{plano_referencia}'",
      "descricao": "Nome da conta",
      "nova_descricao": "Caso a intenção seja ALTERAR e houver novo nome, caso contrário null",
      "valor": float_ou_null,
      "tipo": "Saída" ou "Entrada",
      "data_vencimento": "YYYY-MM-DD",
      "mes_referencia": int_ou_null,
      "permite_parcial": boolean,
      "recorrencia_tipo": "TODOS" | "PERIODO" | null,
      "mes_inicio": "YYYY-MM-01" | null,
      "mes_fim": "YYYY-MM-01" | null
    }}
    """

  response = client_groq.chat.completions.create(
      model="llama-3.3-70b-versatile",
      messages=[{"role": "user", "content": prompt}],
      temperature=0.1,
      response_format={"type": "json_object"},
  )

  texto_limpo = response.choices[0].message.content.strip()
  return json.loads(texto_limpo)


def buscar_planejamento_existente(
    supabase,
    usuario_id,
    projeto_id,
    descricao,
    incluir_realizados=False,
    mes_referencia=None,
    valor_filtro=None,
    data_venc_filtro=None,
):
  """Busca lançamentos no Supabase com suporte a busca flexível e filtro por valor/data exatos para evitar exclusões/alterações erradas."""
  if not descricao or len(descricao.strip()) < 2:
    return None

  try:
    desc_norm = normalizar_texto(descricao)
    desc_limpa = limpar_descricao_busca(descricao)

    query = supabase.table("lancamentos").select("*").eq(
        "usuario_id", str(usuario_id)
    )

    if not incluir_realizados:
      query = query.neq("status", "Realizado")

    if projeto_id and projeto_id != "Padrão":
      query = query.eq("projeto_id", str(projeto_id))

    res = query.execute()

    if not res or not res.data:
      if projeto_id and projeto_id != "Padrão":
        res = (
            supabase.table("lancamentos")
            .select("*")
            .eq("usuario_id", str(usuario_id))
            .neq("status", "IGNORE" if incluir_realizados else "Realizado")
            .execute()
        )

    if not res or not res.data:
      return None

    candidatos = res.data

    # Filtragem por mês de referência
    if mes_referencia is not None:
      candidatos_mes = []
      for item in candidatos:
        dt_str = item.get("data_vencimento") or item.get("data")
        if dt_str:
          try:
            dt_obj = datetime.strptime(str(dt_str)[:10], "%Y-%m-%d")
            if dt_obj.month == int(mes_referencia):
              candidatos_mes.append(item)
          except Exception:
            pass
      if candidatos_mes:
        candidatos = candidatos_mes

    # Filtragem por correspondência de nomes
    candidatos_nome = []
    palavras_busca = [p for p in desc_limpa.split() if len(p) >= 2]

    for item in candidatos:
      d_banco = normalizar_texto(item.get("descricao", ""))
      d_banco_limpo = limpar_descricao_busca(item.get("descricao", ""))
      palavras_banco = [p for p in d_banco_limpo.split() if len(p) >= 2]

      # Match exato ou interseção de palavras
      if (
          desc_norm == d_banco
          or desc_limpa == d_banco_limpo
          or len(set(palavras_busca).intersection(set(palavras_banco))) >= 1
      ):
        candidatos_nome.append(item)

    if not candidatos_nome:
      return None

    # Se o usuário citou um valor exato, filtra preferencialmente por ele
    if valor_filtro and float(valor_filtro) > 0:
      candidatos_valor = [
          c
          for c in candidatos_nome
          if abs(
              float(
                  c.get("valor_plan") or c.get("valor_real") or c.get("valor") or 0
              )
              - float(valor_filtro)
          )
          < 0.01
      ]
      if candidatos_valor:
        candidatos_nome = candidatos_valor

    # Se o usuário citou data específica, desempata pela data
    if data_venc_filtro:
      candidatos_data = [
          c
          for c in candidatos_nome
          if str(c.get("data_vencimento") or c.get("data"))[:10]
          == str(data_venc_filtro)[:10]
      ]
      if candidatos_data:
        return candidatos_data[0]

    return candidatos_nome[0]

  except Exception as e:
    print(f"Erro na busca de planejamento: {e}")

  return None


def formatar_moeda_br(valor):
  """Auxiliar para formatar valores no padrão R$ 1.234,56."""
  try:
    val = float(valor or 0.0)
    return (
        f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
  except Exception:
    return "R$ 0,00"


def executar_acao_no_supabase(supabase, usuario_id, dados):
  """Executa inclusão, alteração, baixa, lançamento parcial ou exclusão no Supabase."""
  intencao = dados.get("intencao")
  projeto_id = str(dados.get("projeto_id"))
  descricao = dados.get("descricao")
  valor = float(dados.get("valor") or 0.0)
  
  # AJUSTE DE FUSO HORÁRIO BRASÍLIA
  data_hoje = obter_hoje_brasil().strftime("%Y-%m-%d")
  data_venc = dados.get("data_vencimento") or data_hoje
  permite_parcial = bool(dados.get("permite_parcial", False))

  tipo_fluxo = dados.get("tipo", "Saída")
  if tipo_fluxo not in ["Entrada", "Saída"]:
    tipo_fluxo = "Saída"

  id_existente = dados.get("id_existente")

  # AÇÃO: EXCLUIR
  if intencao == "EXCLUIR":
    if id_existente:
      supabase.table("lancamentos").delete().eq("id", id_existente).execute()
      return f"🗑️ Lançamento **{descricao}** excluído com sucesso!"
    else:
      return (
          f"⚠️ Não foi possível localizar o lançamento **{descricao}** para"
          " exclusão."
      )

  # AÇÃO: ALTERAR
  if intencao == "ALTERAR":
    if id_existente:
      nova_desc = dados.get("nova_descricao") or descricao
      payload_alterar = {
          "descricao": nova_desc,
          "valor_plan": valor,
          "data_vencimento": data_venc,
          "data": data_venc,
          "tipo": tipo_fluxo,
          "projeto_id": projeto_id,
          "permite_parcial": permite_parcial,
      }
      supabase.table("lancamentos").update(payload_alterar).eq(
          "id", id_existente
      ).execute()
      return f"✏️ Lançamento **{nova_desc}** alterado com sucesso!"
    else:
      return (
          f"⚠️ Não foi possível localizar o lançamento **{descricao}** para"
          " alteração."
      )

  # AÇÃO: PARCIAL
  if intencao == "PARCIAL":
    try:
      dt_obj = datetime.strptime(data_venc, "%Y-%m-%d")
      data_primeiro_dia = dt_obj.replace(day=1).strftime("%Y-%m-%d")
    except Exception:
      data_primeiro_dia = obter_hoje_brasil().replace(day=1).strftime("%Y-%m-%d")

    payload_parcial = {
        "projeto_id": projeto_id,
        "usuario_id": str(usuario_id),
        "descricao": descricao,
        "data": data_primeiro_dia,
        "data_vencimento": data_primeiro_dia,
        "tipo": tipo_fluxo,
        "valor_plan": 0,
        "valor_real": 0,
        "parcial_real": valor,
        "parcial_data": data_venc,
        "status": "Realizado",
        "permite_parcial": False,
    }
    supabase.table("lancamentos").insert(payload_parcial).execute()

    dt_efetiva_fmt = datetime.strptime(data_venc, "%Y-%m-%d").strftime(
        "%d/%m/%Y"
    )
    return (
        f"✅ Lançamento parcial de **{formatar_moeda_br(valor)}** registrado em"
        f" **{descricao}** para o dia **{dt_efetiva_fmt}**!"
    )

  # AÇÃO: REALIZAR / CONSULTAR
  if intencao in ["REALIZAR", "CONSULTAR"]:
    if id_existente:
      payload_update = {
          "valor_real": valor,
          "status": "Realizado",
          "data_vencimento": data_venc,
      }
      supabase.table("lancamentos").update(payload_update).eq(
          "id", id_existente
      ).execute()
      return (
          f"✅ Lançamento **{descricao}** baixado como **Realizado** no valor"
          f" de {formatar_moeda_br(valor)}!"
      )
    else:
      payload_direto = {
          "projeto_id": projeto_id,
          "usuario_id": str(usuario_id),
          "descricao": descricao,
          "data": data_venc,
          "data_vencimento": data_venc,
          "tipo": tipo_fluxo,
          "valor_plan": 0,
          "valor_real": valor,
          "status": "Realizado",
          "parcial_real": 0,
          "permite_parcial": False,
      }
      supabase.table("lancamentos").insert(payload_direto).execute()
      return (
          f"✅ Lançamento **{descricao}** ({formatar_moeda_br(valor)})"
          " registrado e baixado com sucesso!"
      )

  # AÇÃO: PROJETAR
  elif intencao == "PROJETAR":
    recorrencia_tipo = dados.get("recorrencia_tipo")
    mes_inicio_str = dados.get("mes_inicio")
    mes_fim_str = dados.get("mes_fim")

    datas_para_inserir = []

    if permite_parcial:
      try:
        dt_base = datetime.strptime(data_venc, "%Y-%m-%d").replace(day=1)
      except Exception:
        dt_base = obter_hoje_brasil().replace(day=1)

      if recorrencia_tipo == "TODOS":
        ano_atual = dt_base.year
        datas_para_inserir = [
            date(ano_atual, m, 1).strftime("%Y-%m-%d") for m in range(1, 13)
        ]

      elif recorrencia_tipo == "PERIODO" and mes_inicio_str and mes_fim_str:
        try:
          dt_ini = datetime.strptime(mes_inicio_str, "%Y-%m-%d").replace(day=1)
          dt_fim = datetime.strptime(mes_fim_str, "%Y-%m-%d").replace(day=1)
          curr = dt_ini
          while curr <= dt_fim:
            datas_para_inserir.append(curr.strftime("%Y-%m-%d"))
            if curr.month == 12:
              curr = date(curr.year + 1, 1, 1)
            else:
              curr = date(curr.year, curr.month + 1, 1)
        except Exception:
          datas_para_inserir = [dt_base.strftime("%Y-%m-%d")]
      else:
        datas_para_inserir = [dt_base.strftime("%Y-%m-%d")]

    else:
      datas_para_inserir = [data_venc]

    payloads = []
    for dt_ins in datas_para_inserir:
      payloads.append({
          "projeto_id": projeto_id,
          "usuario_id": str(usuario_id),
          "descricao": descricao,
          "data": dt_ins,
          "data_vencimento": dt_ins,
          "tipo": tipo_fluxo,
          "valor_plan": valor,
          "valor_real": 0,
          "status": "Planejado",
          "parcial_real": 0,
          "permite_parcial": permite_parcial,
      })

    supabase.table("lancamentos").insert(payloads).execute()

    qtd = len(payloads)
    if qtd > 1:
      return (
          f"✅ {qtd} lançamentos de **{descricao}** ({formatar_moeda_br(valor)})"
          " projetados com sucesso (Permite Parciais)!"
      )

    dt_venc_fmt = datetime.strptime(
        datas_para_inserir[0], "%Y-%m-%d"
    ).strftime("%d/%m/%Y")
    info_parcial = " (Permite Parciais)" if permite_parcial else ""
    return (
        f"✅ Lançamento **{descricao}** ({formatar_moeda_br(valor)}) com"
        f" vencimento para **{dt_venc_fmt}**{info_parcial} projetado com"
        " sucesso!"
    )

  return "Ação realizada com sucesso!"


def fechar_modal_voz():
  """Reset de estados ao fechar o modal."""
  st.session_state.etapa_voz = "gravacao"
  st.session_state.dados_interpretados = None
  st.session_state.hash_ultimo_audio = None
  st.session_state.audio_key_id = st.session_state.get("audio_key_id", 0) + 1
  st.session_state.abrir_modal_orcas = False
  st.session_state.abrir_modal_voz = False


@st.dialog("🎙️ Conversar com o ORCAS")
def exibir_modal_voz_orcas(supabase, id_usuario, planos_disponiveis=None):
  st.write("👋 **Olá! Em que posso ajudar nos seus lançamentos hoje?**")

  if not planos_disponiveis:
    planos_disponiveis = buscar_planos_do_usuario(supabase, id_usuario)

  plano_ativo = st.session_state.get("projeto_ativo") or st.session_state.get(
      "plano_ativo"
  )
  if not plano_ativo and planos_disponiveis:
    plano_ativo = planos_disponiveis[0]

  groq_key = st.secrets.get("GROQ_API_KEY")
  if not groq_key:
    st.error("❌ Chave GROQ_API_KEY não configurada nos Secrets do Streamlit!")
    return

  client_groq = Groq(api_key=groq_key.strip())

  if "etapa_voz" not in st.session_state:
    st.session_state.etapa_voz = "gravacao"
  if "dados_interpretados" not in st.session_state:
    st.session_state.dados_interpretados = None
  if "hash_ultimo_audio" not in st.session_state:
    st.session_state.hash_ultimo_audio = None
  if "audio_key_id" not in st.session_state:
    st.session_state.audio_key_id = 0

  # ETAPA 1: GRAVAÇÃO E PROCESSAMENTO
  if st.session_state.etapa_voz == "gravacao":
    pode_usar, uso_atual, limite_max = verificar_limite_uso(
        supabase, id_usuario
    )

    if not pode_usar:
      st.error(
          "⚠️ **Você atingiu o limite mensal do recurso de voz!**\n\n"
          f"Você utilizou **{uso_atual}/{limite_max}** comandos neste mês."
      )
      return

    st.caption(
        f"📊 Uso do recurso de voz no mês: **{uso_atual}/{limite_max}**"
        " chamadas."
    )

    key_audio = f"audio_input_{st.session_state.audio_key_id}"
    audio_input = st.audio_input("Grave seu comando abaixo:", key=key_audio)

    if audio_input is not None:
      audio_bytes = audio_input.getvalue()
      hash_atual = hash(audio_bytes)

      if hash_atual != st.session_state.hash_ultimo_audio:
        with st.spinner("🤖 ORCAS está processando o áudio..."):
          try:
            incrementar_uso_voz(supabase, id_usuario, uso_atual)

            texto = transcrever_audio_groq(client_groq, audio_bytes)
            dados = processar_texto_groq(
                client_groq, texto, planos_disponiveis, plano_ativo
            )

            st.session_state.hash_ultimo_audio = hash_atual

            intencao = dados.get("intencao")
            incluir_realizados = intencao in ["EXCLUIR", "ALTERAR", "PARCIAL"]

            data_identificada_ia = dados.get("data_vencimento")

            item_existente = None
            if intencao not in ["PROJETAR"]:
              item_existente = buscar_planejamento_existente(
                  supabase,
                  id_usuario,
                  dados.get("projeto_id"),
                  dados.get("descricao", ""),
                  incluir_realizados=incluir_realizados,
                  mes_referencia=dados.get("mes_referencia"),
                  valor_filtro=dados.get("valor"),
                  data_venc_filtro=dados.get("data_vencimento"),
              )

            valor_falado = float(dados.get("valor") or 0.0)

            if item_existente:
              dados["id_existente"] = item_existente.get("id")
              desc_cadastrada = item_existente.get(
                  "descricao"
              ) or dados.get("descricao")
              dados["descricao"] = desc_cadastrada

              if item_existente.get("projeto_id"):
                dados["projeto_id"] = item_existente.get("projeto_id")

              valor_planejado = float(
                  item_existente.get("valor_plan")
                  or item_existente.get("valor_real")
                  or item_existente.get("valor")
                  or 0.0
              )

              dt_banco = item_existente.get(
                  "data_vencimento"
              ) or item_existente.get("data")

              permite_parcial = item_existente.get("permite_parcial", False)
              if permite_parcial or intencao == "PARCIAL":
                dados["intencao"] = "PARCIAL"
                dados["valor"] = valor_falado
                if not data_identificada_ia:
                  dados["data_vencimento"] = obter_hoje_brasil().strftime("%Y-%m-%d")
                else:
                  dados["data_vencimento"] = data_identificada_ia

                dt_venc_fmt = datetime.strptime(
                    dados["data_vencimento"], "%Y-%m-%d"
                ).strftime("%d/%m/%Y")
                dados["mensagem_orcas"] = (
                    f"Identifiquei a conta orçada **{desc_cadastrada}**"
                    " (Permite Parcial).\n\nConfirmar o lançamento parcial"
                    f" de **{formatar_moeda_br(valor_falado)}** na data"
                    f" **{dt_venc_fmt}**?"
                )

              elif intencao == "EXCLUIR":
                dados["valor"] = valor_planejado
                if dt_banco:
                  dados["data_vencimento"] = str(dt_banco)[:10]

                dt_venc_fmt = datetime.strptime(
                    dados["data_vencimento"], "%Y-%m-%d"
                ).strftime("%d/%m/%Y")
                dados["mensagem_orcas"] = (
                    f"Encontrei o lançamento **{desc_cadastrada}** no valor"
                    f" de **{formatar_moeda_br(valor_planejado)}**"
                    f" (Vencimento: **{dt_venc_fmt}**).\n\nDeseja realmente"
                    " **EXCLUIR** este lançamento?"
                )

              elif intencao == "ALTERAR":
                if not data_identificada_ia and dt_banco:
                  dados["data_vencimento"] = str(dt_banco)[:10]

                dados["valor"] = (
                    valor_falado if valor_falado > 0.0 else valor_planejado
                )
                dados["mensagem_orcas"] = (
                    f"Encontrei o lançamento **{desc_cadastrada}**. Você pode"
                    " ajustar os dados abaixo para confirmar a alteração:"
                )

              else:
                if not data_identificada_ia and dt_banco:
                  dados["data_vencimento"] = str(dt_banco)[:10]

                valor_final = (
                    valor_falado if valor_falado > 0.0 else valor_planejado
                )
                dados["valor"] = valor_final
                dt_venc_fmt = datetime.strptime(
                    dados["data_vencimento"], "%Y-%m-%d"
                ).strftime("%d/%m/%Y")

                dados["mensagem_orcas"] = (
                    f"Encontrei a conta **{desc_cadastrada}** com o valor"
                    f" planejado de **{formatar_moeda_br(valor_planejado)}**"
                    f" (Vencimento: **{dt_venc_fmt}**).\n\nEsta é a conta a"
                    " que você se refere e confirma a baixa?"
                )

            else:
              dados["id_existente"] = None
              dados["valor"] = valor_falado

              if not dados.get("data_vencimento"):
                dados["data_vencimento"] = obter_hoje_brasil().strftime("%Y-%m-%d")

              dt_venc_fmt = datetime.strptime(
                  dados["data_vencimento"], "%Y-%m-%d"
              ).strftime("%d/%m/%Y")

              if intencao == "EXCLUIR":
                dados["mensagem_orcas"] = (
                    "Não encontrei nenhum lançamento com o nome"
                    f" **{dados.get('descricao')}** para ser excluído."
                )
              elif intencao == "ALTERAR":
                dados["mensagem_orcas"] = (
                    "Não encontrei o lançamento"
                    f" **{dados.get('descricao')}** para ser alterado."
                )
              elif intencao == "PROJETAR":
                str_parcial = (
                    " (Permite Parciais)"
                    if dados.get("permite_parcial")
                    else ""
                )
                dados["mensagem_orcas"] = (
                    f"Deseja incluir o lançamento **{dados.get('descricao')}**"
                    f" no valor de **{formatar_moeda_br(valor_falado)}** com"
                    f" vencimento para **{dt_venc_fmt}**{str_parcial}?"
                )
              elif valor_falado > 0.0:
                dados["mensagem_orcas"] = (
                    "Não encontrei um planejamento pendente para"
                    f" **{dados.get('descricao')}**. Deseja realizar um novo"
                    " lançamento direto no valor de"
                    f" **{formatar_moeda_br(valor_falado)}**?"
                )
              else:
                dados["mensagem_orcas"] = (
                    f"Não encontrei a conta **{dados.get('descricao')}**"
                    " pendente nos planejamentos e nenhum valor foi informado."
                    " Por favor, tente novamente informando o valor pago."
                )

            st.session_state.dados_interpretados = dados
            st.session_state.etapa_voz = "confirmacao"
            st.rerun()

          except Exception as e:
            st.error(f"Erro no processamento: {e}")

  # ETAPA 2: CONFIRMAÇÃO E EDIÇÃO DOS DADOS PELO USUÁRIO
  elif st.session_state.etapa_voz == "confirmacao":
    dados = st.session_state.dados_interpretados or {}

    st.info(f'🗣️ **Você disse:** "{dados.get("transcricao", "")}"')

    with st.container(border=True):
      st.markdown(f"🤖 **ORCAS:** {dados.get('mensagem_orcas')}")
      st.markdown("---")

      with st.form("form_confirmacao_orcas"):
        col_1, col_2 = st.columns(2)

        acoes_opcoes = ["REALIZAR", "PROJETAR", "PARCIAL", "ALTERAR", "EXCLUIR"]
        intencao_atual = dados.get("intencao", "REALIZAR")
        idx_acao = (
            acoes_opcoes.index(intencao_atual)
            if intencao_atual in acoes_opcoes
            else 0
        )

        with col_1:
          nova_intencao = st.selectbox("Ação", acoes_opcoes, index=idx_acao)

          idx_plano = 0
          if dados.get("projeto_id") in planos_disponiveis:
            idx_plano = planos_disponiveis.index(dados.get("projeto_id"))

          novo_plano = st.selectbox(
              "Plano / Projeto", planos_disponiveis, index=idx_plano
          )

          desc_inicial = (
              dados.get("nova_descricao")
              if dados.get("nova_descricao")
              else dados.get("descricao", "")
          )
          nova_descricao = st.text_input("Descrição", value=desc_inicial)

        with col_2:
          tipo_opcoes = ["Saída", "Entrada"]
          idx_tipo = 0 if dados.get("tipo", "Saída") == "Saída" else 1
          novo_tipo = st.selectbox("Tipo", tipo_opcoes, index=idx_tipo)

          valor_inicial = float(dados.get("valor") or 0.0)
          novo_valor = st.number_input(
              "Valor (R$)", value=valor_inicial, step=5.0, format="%.2f"
          )

          try:
            dt_val = datetime.strptime(
                dados.get("data_vencimento", str(obter_hoje_brasil())), "%Y-%m-%d"
            ).date()
          except Exception:
            dt_val = obter_hoje_brasil()

          nova_data_venc = st.date_input(
              "Data de Vencimento / Ocorrência",
              value=dt_val,
              format="DD/MM/YYYY",
          )

        novo_permite_parcial = st.checkbox(
            "Permite Lançamento Parcial?",
            value=bool(dados.get("permite_parcial", False)),
        )

        st.markdown("---")
        btn_salvar, btn_refazer, btn_cancelar = st.columns(3)

        with btn_salvar:
          texto_botao = (
              "🗑️ Confirmar Exclusão"
              if nova_intencao == "EXCLUIR"
              else "✅ Confirmar e Gravar"
          )
          submit_salvar = st.form_submit_button(
              texto_botao, type="primary", use_container_width=True
          )

        with btn_refazer:
          submit_refazer = st.form_submit_button(
              "🔄 Falar Novamente", use_container_width=True
          )

        with btn_cancelar:
          submit_cancelar = st.form_submit_button(
              "❌ Cancelar / Sair", use_container_width=True
          )

      if submit_salvar:
        dados_atualizados = {
            "intencao": nova_intencao,
            "projeto_id": novo_plano,
            "descricao": nova_descricao,
            "valor": novo_valor,
            "tipo": novo_tipo,
            "data_vencimento": nova_data_venc.strftime("%Y-%m-%d"),
            "permite_parcial": novo_permite_parcial,
            "recorrencia_tipo": dados.get("recorrencia_tipo"),
            "mes_inicio": dados.get("mes_inicio"),
            "mes_fim": dados.get("mes_fim"),
            "id_existente": dados.get("id_existente"),
        }
        try:
          msg_sucesso = executar_acao_no_supabase(
              supabase, id_usuario, dados_atualizados
          )
          st.success(msg_sucesso)
          time.sleep(1.2)
          fechar_modal_voz()
          st.rerun()
        except Exception as e:
          st.error(f"❌ Erro ao processar ação: {e}")

      elif submit_refazer:
        st.session_state.etapa_voz = "gravacao"
        st.session_state.dados_interpretados = None
        st.session_state.hash_ultimo_audio = None
        st.session_state.audio_key_id += 1
        st.rerun()

      elif submit_cancelar:
        fechar_modal_voz()
        st.rerun()