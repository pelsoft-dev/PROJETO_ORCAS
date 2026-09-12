import calendar
from datetime import datetime, timedelta, timezone
import re
import streamlit as st

# Importando a ajuda do arquivo dedicado para Projetar
from orcas_v01_ajuda_projetar import renderizar_ajuda_projetar


def executar_inclusao_projetar(
    supabase,
    projeto_id,
    usuario_id,
    descricao,
    complemento_texto,
    valor_float,
    tipo,
    dia_mes="",
    dia_semana="",
    dia_especifico=None,
    n_ocorrencias=0,
    regra_fds="Manter",
    dt_inicio=None,
    dt_fim=None,
    is_cartao=False,
    dia_corte=31,
    usar_corrc=False,
    c_quando="Todo mês",
    c_base="Média dos Realizados",
    v_pct_float=0.0,
    permitir_parcial=False,
    p_depois="Zera o Realizado",
):
  """Motor de execução do Projetar isolado para uso tanto na interface do Projetar quanto no PorVoz."""
  if not descricao or not str(descricao).strip():
    return False, "PARA INCLUIR É OBRIGATÓRIO ENTRAR COM UMA DESCRIÇÃO", 0

  d_m_final = dia_mes
  if permitir_parcial:
    d_m_final = "1"

  curr = dt_inicio
  if permitir_parcial and curr:
    curr = curr.replace(day=1)

  v_calc = float(valor_float or 0.0)
  v_pct = float(v_pct_float or 0.0)
  lista_bulk = []
  gerados = 0
  d_map = {
      "Segunda": 0,
      "Terça": 1,
      "Quarta": 2,
      "Quinta": 3,
      "Sexta": 4,
      "Sábado": 5,
      "Domingo": 6,
  }

  comp_base = complemento_texto.strip() if complemento_texto else ""
  num_atual = None
  sufixo = ""
  zeros = 0

  if comp_base:
    match_de = re.search(
        r"^\s*(\d+)\s+de\s+(\d+)(.*)$", comp_base, re.IGNORECASE
    )
    if match_de:
      num_str = match_de.group(1)
      num_atual = int(num_str)
      zeros = len(num_str)
      total_tt = int(match_de.group(2))
      sufixo = f" de {match_de.group(2)}{match_de.group(3)}"

      if n_ocorrencias == 0 and total_tt >= num_atual:
        n_ocorrencias = (total_tt - num_atual) + 1
    elif comp_base.isdigit():
      num_atual = int(comp_base)
      zeros = len(comp_base)

  limite_loop = (
      dt_fim
      if n_ocorrencias == 0
      else (dt_inicio + timedelta(days=3650) if dt_inicio else dt_fim)
  )

  while curr and limite_loop and curr <= limite_loop:
    match_dm = False

    if "/" in str(d_m_final):
      try:
        dia_a, mes_a = map(int, str(d_m_final).split("/"))
        if curr.day == dia_a and curr.month == mes_a:
          match_dm = True
      except Exception:
        pass
    elif str(d_m_final).isdigit():
      dia_req = int(d_m_final)
      ultimo_dia_mes = calendar.monthrange(curr.year, curr.month)[1]
      dia_alvo = min(dia_req, ultimo_dia_mes)
      if curr.day == dia_alvo:
        match_dm = True
    else:
      match_dm = (
          d_m_final == "" or d_m_final == "*" or str(curr.day) == str(d_m_final)
      )

    if (
        (dia_especifico is None or curr == dia_especifico)
        and match_dm
        and (dia_semana == "" or curr.weekday() == d_map.get(dia_semana, -1))
    ):
      processar = False
      if permitir_parcial:
        dt_ref_parcial = curr.replace(day=1)
        if dt_inicio.replace(day=1) <= dt_ref_parcial <= dt_fim:
          processar = True
      else:
        if dt_inicio <= curr <= dt_fim:
          processar = True

      if processar:
        dt_f = curr
        if permitir_parcial:
          dt_f = dt_f.replace(day=1)
        elif regra_fds != "Manter" and dt_f.weekday() >= 5:
          if regra_fds == "Posterga":
            dt_f += timedelta(days=(2 if dt_f.weekday() == 5 else 1))
          elif regra_fds == "Antecipa":
            dt_f -= timedelta(days=(1 if dt_f.weekday() == 5 else 2))

        if permitir_parcial or (dt_inicio <= dt_f <= dt_fim):
          comp_gerado = complemento_texto
          if num_atual is not None:
            comp_gerado = f"{str(num_atual + gerados).zfill(zeros)}{sufixo}"

          nome_final = (
              f"{descricao} {comp_gerado}".strip() if comp_gerado else descricao
          )

          lista_bulk.append({
              "projeto_id": projeto_id,
              "usuario_id": usuario_id,
              "data": dt_f.strftime("%Y-%m-%d"),
              "data_vencimento": dt_f.strftime("%Y-%m-%d"),
              "descricao": nome_final,
              "valor_plan": float(v_calc),
              "valor_real": 0.0,
              "tipo": tipo,
              "status": "Planejado",
              "permite_parcial": bool(permitir_parcial),
              "usar_media": bool(
                  usar_corrc and c_base == "Média dos Realizados"
              ),
              "complemento_texto": comp_gerado if comp_gerado else None,
              "correcao_freq": c_quando if usar_corrc else None,
              "correcao_valor": (
                  float(v_pct) if c_base == "Percentual Fixo (%)" else 0.0
              ),
              "regra_parcial": str(p_depois),
              "cc_tipo": "$CCP" if is_cartao else None,
              "cc_dia_corte": int(dia_corte) if is_cartao else None,
          })
          gerados += 1
          if (
              usar_corrc
              and c_quando == "Todo mês"
              and c_base == "Percentual Fixo (%)"
          ):
            v_calc *= 1 + v_pct

    if n_ocorrencias > 0 and gerados >= n_ocorrencias:
      break
    curr += timedelta(days=1)

  if lista_bulk:
    try:
      supabase.table("lancamentos").insert(lista_bulk).execute()
      return True, f"Sucesso! {len(lista_bulk)} lançamentos gerados.", len(
          lista_bulk
      )
    except Exception as e:
      return False, f"Erro no Supabase: {e}", 0

  return (
      False,
      "Nenhum lançamento gerado. As datas da regra caem fora do intervalo"
      " Início/Até.",
      0,
  )


def exibir_projetar(
    df, supabase, ID_USUARIO_LOGADO, d_ini_db, d_fim_db, parse_moeda
):
  # --- CABEÇALHO ALINHADO COM BOTÃO DE AJUDA ---
  col_titulo, col_ajuda = st.columns([4, 1])

  with col_titulo:
    st.markdown(
        f'<div class="titulo-tela" style="margin-top:0px;">Projetar:'
        f" {st.session_state.projeto_ativo}</div>",
        unsafe_allow_html=True,
    )

  with col_ajuda:
    st.markdown(
        """
            <style>
            div.stButton > button:first-child {
                background-color: #007ba7 !important;
                color: white !important;
                border: none !important;
            }
            div.stButton > button:first-child:hover {
                background-color: #005f81 !important;
                color: white !important;
            }
            </style>
        """,
        unsafe_allow_html=True,
    )

    if st.button("AJUDA", type="primary", use_container_width=True):
      st.session_state["exibir_ajuda_projetar"] = not st.session_state.get(
          "exibir_ajuda_projetar", False
      )
      st.rerun()

  # --- EXIBIÇÃO DA TELA DE AJUDA SE O BOTÃO FOR CLICADO ---
  if st.session_state.get("exibir_ajuda_projetar", False):
    renderizar_ajuda_projetar()

  # --- TRATAMENTO SEGURO DE DATAS VINDAS DO BANCO (d_ini_db e d_fim_db) ---
  def converter_para_date(val):
    if isinstance(val, str):
      try:
        return datetime.strptime(val[:10], "%Y-%m-%d").date()
      except Exception:
        return None
    elif isinstance(val, datetime):
      return val.date()
    return val

  dt_ini_valida = converter_para_date(d_ini_db)
  dt_fim_valida = converter_para_date(d_fim_db)

  # Ajuste de Fuso Horário para Jundiaí/Brasília (UTC-3)
  fuso_br = timezone(timedelta(hours=-3))
  hoje_br = datetime.now(fuso_br).date()

  # Define a data de início padrão para o dia 01 do mês corrente
  inicio_padrao = hoje_br.replace(day=1)

  if "limpar_cont" not in st.session_state:
    st.session_state.limpar_cont = 0
  if "bloqueio_excludente" not in st.session_state:
    st.session_state.bloqueio_excludente = False

  # Busca segura da mensagem de sucesso
  if st.session_state.get("msg_sucesso"):
    st.success(st.session_state["msg_sucesso"])
    st.session_state["msg_sucesso"] = None

  # --- (1) TRAVA DE SEGURANÇA EXCLUDENTE ---
  if st.session_state.bloqueio_excludente:
    st.error(
        "AS OPÇÕES (DIA DO MÊS, DIA DA SEMANA E DIA ESPECÍFICO) SÃO EXCLUDENTES"
        " E PORTANTO O ORCAS ACEITARÁ APENAS UMA DELAS"
    )
    if st.button("OK", key="btn_ok_erro"):
      st.session_state.bloqueio_excludente = False
      st.session_state.limpar_cont += 1
      st.rerun()
    st.stop()

  v = st.session_state.limpar_cont

  col_d1, col_d2 = st.columns([4, 2])
  desc = col_d1.text_input("Descrição", key=f"pj_d_{v}")
  comp_txt = col_d2.text_input("Complemento", key=f"pj_comp_{v}")

  col_v, col_t = st.columns(2)
  v_t = col_v.text_input("Valor", "0,00", key=f"pj_val_{v}")
  tipo = col_t.selectbox("Tipo", ["Saída", "Entrada"], key=f"pj_tipo_{v}")

  with st.expander("Recorrência e Datas"):
    c1, c2, c3 = st.columns(3)
    d_m = c1.text_input("Dia (1-31, DD/MM ou *)", "", key=f"pj_dm_{v}")
    d_s = c2.selectbox(
        "Dia da Semana",
        ["", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"],
        key=f"pj_ds_{v}",
    )
    d_e = c3.date_input(
        "Dia Específico", value=None, format="DD/MM/YYYY", key=f"pj_de_{v}"
    )

    op_preenchidas = 0
    if d_m != "":
      op_preenchidas += 1
    if d_s != "":
      op_preenchidas += 1
    if d_e is not None:
      op_preenchidas += 1

    if op_preenchidas > 1:
      st.session_state.bloqueio_excludente = True
      st.rerun()

    n_ocorrencias = st.number_input(
        "Nº de Ocorrências (0 = usar Data Até)",
        min_value=0,
        step=1,
        key=f"pj_noc_{v}",
    )

    col_fds, col_obs = st.columns([1, 1])
    with col_fds:
      fds = st.radio(
          "Se cair em Fim de Semana:",
          ["Manter", "Antecipa", "Posterga"],
          horizontal=True,
          key=f"pj_fds_{v}",
      )
    with col_obs:
      st.markdown(
          """
                <div style="margin-top: 25px; font-size: 11px; color: #555555; line-height: 1.3;">
                    <i><b>Obs:</b> Se você escolher os dias 29, 30 ou 31 e o mês não possuir essa data, o lançamento será feito no último dia desse mês.</i>
                </div>
                """,
          unsafe_allow_html=True,
      )

    c_i, c_f = st.columns(2)

    val_i_p = inicio_padrao
    if dt_ini_valida and val_i_p < dt_ini_valida:
      val_i_p = dt_ini_valida
    elif dt_fim_valida and val_i_p > dt_fim_valida:
      val_i_p = dt_fim_valida

    i_p = c_i.date_input(
        "Início",
        value=val_i_p,
        min_value=dt_ini_valida,
        max_value=dt_fim_valida,
        format="DD/MM/YYYY",
        key=f"pj_data_ini_{v}",
    )

    val_f_p = dt_fim_valida if dt_fim_valida else hoje_br
    if dt_ini_valida and val_f_p < dt_ini_valida:
      val_f_p = dt_ini_valida

    f_p = c_f.date_input(
        "Até",
        value=val_f_p,
        min_value=dt_ini_valida,
        max_value=dt_fim_valida,
        format="DD/MM/YYYY",
        key=f"pj_data_fim_{v}",
    )

  with st.expander("Projeção Avançada", expanded=False):
    st.markdown("**Cartão de Crédito**")
    col_cc1, col_cc2 = st.columns([2, 5])
    is_cartao = col_cc1.checkbox("Cartão de Crédito", key=f"pj_is_cc_{v}")

    ult_dia_mes_atual = calendar.monthrange(hoje_br.year, hoje_br.month)[1]
    dia_corte = col_cc2.number_input(
        "A partir deste dia, as despesas serão lançadas na próxima fatura:",
        min_value=1,
        max_value=31,
        value=ult_dia_mes_atual,
        step=1,
        key=f"pj_corte_cc_{v}",
    )

    st.divider()
    st.markdown("**Regras de Correção Automática**")
    col_c1, col_c2, col_c3 = st.columns([2, 2, 3])
    usar_corrc = col_c1.checkbox("Corrigir este valor?", key=f"pj_cor_{v}")
    c_quando = col_c2.selectbox(
        "Quando:", ["Todo mês", "Todo ano"], key=f"pj_qdo_{v}"
    )
    c_base = col_c3.selectbox(
        "Com base em:",
        ["Média dos Realizados", "Percentual Fixo (%)", "IGPM"],
        key=f"pj_base_{v}",
    )
    c_val_fixo = st.text_input(
        "Valor do Percentual (se fixo)", "0,00", key=f"pj_vfixo_{v}"
    )

    st.divider()
    st.markdown("**Realizações Parciais e Resíduos**")
    col_p1, col_p2 = st.columns([2, 5])
    permitir_parcial = col_p1.checkbox("Permitir parciais?", key=f"pj_parc_{v}")

    opcoes_residuo = [
        "Zera o Realizado",
        "Adicione a diferença (P-R) no próximo Planejado",
        "Copia a diferença (P-R) no próximo Planejado",
    ]
    p_depois = col_p2.selectbox(
        "No último dia do Mês:", opcoes_residuo, index=0, key=f"pj_pdep_{v}"
    )

  btn_col1, btn_col2, _ = st.columns([1, 1, 2])

  if btn_col1.button("Incluir", use_container_width=True):
    uid_local = st.session_state.get("CHAVE_MESTRA_UUID")
    v_calc = parse_moeda(v_t)
    v_pct = parse_moeda(c_val_fixo) / 100

    sucesso, msg, _ = executar_inclusao_projetar(
        supabase=supabase,
        projeto_id=st.session_state.projeto_ativo,
        usuario_id=uid_local,
        descricao=desc,
        complemento_texto=comp_txt,
        valor_float=v_calc,
        tipo=tipo,
        dia_mes=d_m,
        dia_semana=d_s,
        dia_especifico=d_e,
        n_ocorrencias=n_ocorrencias,
        regra_fds=fds,
        dt_inicio=i_p,
        dt_fim=f_p,
        is_cartao=is_cartao,
        dia_corte=dia_corte,
        usar_corrc=usar_corrc,
        c_quando=c_quando,
        c_base=c_base,
        v_pct_float=v_pct,
        permitir_parcial=permitir_parcial,
        p_depois=p_depois,
    )

    if sucesso:
      st.session_state["msg_sucesso"] = msg
      st.session_state.limpar_cont += 1
      st.rerun()
    else:
      st.error(msg)

  if btn_col2.button("Excluir", use_container_width=True):
    if not desc or desc.strip() == "":
      st.error("PARA INCLUIR OU EXCLUIR É OBRIGATÓRIO ENTRAR COM UMA DESCRIÇÃO")
    else:
      st.session_state.confirmar_exclusao_ativa = True

  if st.session_state.get("confirmar_exclusao_ativa", False):
    nome_busca = f"{desc} {comp_txt}".strip() if comp_txt else desc
    uid_exec = st.session_state.get("CHAVE_MESTRA_UUID")
    msg_confirma = (
        f"VOCÊ DESEJA EXCLUIR O LANÇAMENTO {nome_busca} DO DIA"
        f" {d_e.strftime('%d/%m/%Y') if d_e else ''}. SIM/NÃO?"
        if d_e
        else f"VOCÊ DESEJA EXCLUIR TODOS OS LANÇAMENTOS DE {nome_busca} DO"
        f" PERÍODO DE {i_p.strftime('%d/%m/%Y')} A {f_p.strftime('%d/%m/%Y')}."
        " SIM/NÃO?"
    )
    st.warning(msg_confirma)
    exc_c1, exc_c2 = st.columns(2)
    if exc_c1.button("SIM", key="btn_conf_sim"):
      query = (
          supabase.table("lancamentos")
          .delete()
          .eq("projeto_id", st.session_state.projeto_ativo)
          .eq("usuario_id", uid_exec)
          .eq("descricao", nome_busca)
      )
      if d_e:
        res_exc = query.eq("data", d_e.strftime("%Y-%m-%d")).execute()
      else:
        res_exc = (
            query.gte("data", i_p.strftime("%Y-%m-%d"))
            .lte("data", f_p.strftime("%Y-%m-%d"))
            .execute()
        )

      qtd_excluidos = len(res_exc.data) if hasattr(res_exc, "data") else 0
      st.session_state["msg_sucesso"] = (
          f"Sucesso! {qtd_excluidos} Lançamentos Excluidos."
      )
      st.session_state.confirmar_exclusao_ativa = False
      st.rerun()
    if exc_c2.button("NÃO", key="btn_conf_nao"):
      st.session_state.confirmar_exclusao_ativa = False
      st.rerun()