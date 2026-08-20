import calendar
from datetime import datetime, timedelta
import zoneinfo
import pandas as pd
from orcas_v01_ajuda_conciliacao import renderizar_ajuda_conciliacao
import streamlit as st

# ==============================================================================
# ENGINES & REGRAS DE NEGÓCIO (Exportadas para a Conciliação e Módulo por Voz)
# ==============================================================================


def buscar_dados_cartao(supabase, df, nome_cartao):
  """Busca o dia de corte e o dia de vencimento do cartão ($CCP).

  Caso não encontre no df local, realiza uma busca direta no Supabase.
  """
  if not nome_cartao or str(nome_cartao).strip().upper() == "NENHUM":
    return 21, 27

  nome_busca = str(nome_cartao).strip().upper()

  # 1. Tenta buscar no DataFrame local (se fornecido)
  if df is not None and not df.empty and "cc_tipo" in df.columns:
    df_ccp = df[
        (
            df["cc_tipo"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(["$CCP", "CCP", "'Z $CCP", "Z|$CCP"])
        )
        & (
            df["descricao"].fillna("").astype(str).str.strip().str.upper()
            == nome_busca
        )
    ]
    if not df_ccp.empty:
      row = df_ccp.iloc[0]
      venc = row.get("cc_dia_vencimento")
      corte = row.get("cc_dia_corte")
      if pd.notnull(venc) and pd.notnull(corte):
        return int(corte), int(venc)
      elif pd.notnull(venc):
        venc_int = int(venc)
        corte_calc = venc_int - 6 if venc_int > 6 else venc_int + 24
        return corte_calc, venc_int

  # 2. Se não achou no df local, busca direto no Supabase
  try:
    res = (
        supabase.table("lancamentos")
        .select("cc_dia_corte, cc_dia_vencimento")
        .eq("projeto_id", str(st.session_state.projeto_ativo))
        .ilike("descricao", nome_busca)
        .execute()
    )

    if res.data:
      for item in res.data:
        venc = item.get("cc_dia_vencimento")
        corte = item.get("cc_dia_corte")
        if venc is not None and corte is not None:
          return int(corte), int(venc)
        elif venc is not None:
          venc_int = int(venc)
          corte_calc = venc_int - 6 if venc_int > 6 else venc_int + 24
          return corte_calc, venc_int
  except Exception:
    pass

  return 21, 27


def calcular_vencimento_fatura(data_compra, dia_corte=21, dia_vencimento=27):
  """Calcula a data exata de vencimento da 1ª parcela com base no dia de corte da fatura."""
  corte = int(dia_corte)
  venc = int(dia_vencimento)

  ano = data_compra.year
  mes = data_compra.month

  # Se a compra foi feita no dia do corte ou após, entra na fatura do mês seguinte
  if data_compra.day >= corte:
    mes += 1
    if mes > 12:
      mes = 1
      ano += 1

  dia_final = min(venc, calendar.monthrange(ano, mes)[1])
  return datetime(ano, mes, dia_final).date()


def somar_meses_data(data_fatura_base, i_parcela, dia_vencimento=27):
  """Gera a data de vencimento da N-ésima parcela mantendo o dia fixo da fatura."""
  ano = data_fatura_base.year + (
      (data_fatura_base.month + i_parcela - 1) // 12
  )
  mes = ((data_fatura_base.month + i_parcela - 1) % 12) + 1
  dia_final = min(int(dia_vencimento), calendar.monthrange(ano, mes)[1])
  return datetime(ano, mes, dia_final).date()


def buscar_cartoes_lcp(df):
  """Busca no DataFrame os cartões cadastrados preservando o nome original cadastrado."""
  cartoes_ccp = []
  if df is not None and not df.empty and "cc_tipo" in df.columns:
    df_ccp = df[
        df["cc_tipo"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(["$CCP", "CCP", "'Z $CCP", "Z|$CCP"])
    ]
    if not df_ccp.empty and "descricao" in df_ccp.columns:
      cartoes_ccp = df_ccp["descricao"].dropna().unique().tolist()
      cartoes_ccp = sorted(
          list(set([c.strip() for c in cartoes_ccp if c.strip()]))
      )

  opcoes = ["Nenhum"] + cartoes_ccp + ["+ Outro Cartão..."]
  return opcoes


def atualizar_valor_plan_cartao(
    supabase, df, nome_cartao, dt_vencimento, ID_USUARIO_LOGADO
):
  """Recalcula o valor_plan do Cartão Pai ($CCP) consultando diretamente o Supabase."""
  nome_busca = str(nome_cartao).strip().upper()
  ano_venc = dt_vencimento.year
  mes_venc = dt_vencimento.month

  primeiro_dia_mes = f"{ano_venc:04d}-{mes_venc:02d}-01"
  ultimo_dia_mes = f"{ano_venc:04d}-{mes_venc:02d}-{calendar.monthrange(ano_venc, mes_venc)[1]:02d}"

  try:
    res = (
        supabase.table("lancamentos")
        .select("id, descricao, cc_tipo, valor_plan, data_vencimento")
        .eq("projeto_id", str(st.session_state.projeto_ativo))
        .gte("data_vencimento", primeiro_dia_mes)
        .lte("data_vencimento", ultimo_dia_mes)
        .execute()
    )

    df_db = pd.DataFrame(res.data) if res.data else pd.DataFrame()
  except Exception:
    df_db = pd.DataFrame()

  if not df_db.empty:
    df_ccp = df_db[
        (
            df_db["cc_tipo"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(["$CCP", "CCP", "'Z $CCP", "Z|$CCP"])
        )
        & (
            df_db["descricao"].fillna("").astype(str).str.strip().str.upper()
            == nome_busca
        )
    ]

    mask_lcls = (
        df_db["cc_tipo"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.contains(r"LCL|\$CCL", regex=True)
    ) & (
        df_db["descricao"].fillna("").astype(str).str.strip().str.upper()
        == nome_busca
    )

    soma_lcls = float(df_db[mask_lcls]["valor_plan"].fillna(0).sum())
  else:
    df_ccp = pd.DataFrame()
    soma_lcls = 0.0

  try:
    if not df_ccp.empty:
      id_ccp = df_ccp.iloc[0]["id"]
      supabase.table("lancamentos").update(
          {"valor_plan": round(soma_lcls, 2)}
      ).eq("id", id_ccp).execute()
    else:
      corte, venc = buscar_dados_cartao(supabase, df, nome_cartao)
      dia_final = min(venc, calendar.monthrange(ano_venc, mes_venc)[1])
      dt_exata_ccp = datetime(ano_venc, mes_venc, dia_final).date()

      supabase.table("lancamentos").insert({
          "projeto_id": str(st.session_state.projeto_ativo),
          "usuario_id": str(ID_USUARIO_LOGADO),
          "descricao": nome_cartao,
          "data": dt_exata_ccp.strftime("%Y-%m-%d"),
          "data_vencimento": dt_exata_ccp.strftime("%Y-%m-%d"),
          "tipo": "Saída",
          "valor_plan": round(soma_lcls, 2),
          "valor_real": 0.0,
          "status": "Planejado",
          "cc_tipo": "$CCP",
          "cc_dia_corte": corte,
          "cc_dia_vencimento": venc,
      }).execute()
  except Exception as e:
    st.error(f"Erro ao atualizar Cartão Pai ($CCP): {e}")


def salvar_lancamento_oficial(supabase, usuario_id, dados):
  """MOTOR ÚNICO DE CRIAÇÃO/EDIÇÃO DE LANÇAMENTOS (USADO NA CONCILIAÇÃO E NO PORVOZ)."""
  hoje = datetime.now(zoneinfo.ZoneInfo("America/Sao_Paulo")).date()
  projeto_id = str(
      dados.get("projeto_id") or st.session_state.get("projeto_ativo")
  )
  descricao = str(dados.get("descricao") or "").strip()
  valor = float(dados.get("valor") or 0.0)
  tipo = dados.get("tipo", "Saída")
  dt_venc = dados.get("data_vencimento") or str(hoje)
  cartao = dados.get("cartao")
  parcelas = int(dados.get("parcelas") or 1)
  intencao = dados.get("intencao", "REALIZAR")
  id_existente = dados.get("id_existente")
  permite_parcial = bool(dados.get("permite_parcial"))

  try:
    dt_compra = datetime.strptime(dt_venc, "%Y-%m-%d").date()
  except Exception:
    dt_compra = hoje

  # 1. EXCLUSÃO
  if intencao == "EXCLUIR" and id_existente:
    supabase.table("lancamentos").delete().eq("id", id_existente).execute()
    return f"🗑️ Lançamento **{descricao}** excluído!"

  # 2. CARTÃO DE CRÉDITO
  is_cartao_valido = (
      cartao
      and str(cartao).strip().upper() not in ["NENHUM", "NONE", "NULL", ""]
      and parcelas >= 1
  )

  if is_cartao_valido:
    corte, venc = buscar_dados_cartao(supabase, None, cartao)

    # Vencimento da 1ª parcela considerando o dia de corte da fatura
    dt_1_venc = calcular_vencimento_fatura(
        dt_compra, dia_corte=corte, dia_vencimento=venc
    )

    base_val = round(valor / parcelas, 2)
    residuo = round(valor - (base_val * parcelas), 2)

    # Item mestre: valor_plan = 0, valor_real = total da compra, cc_tipo = LCL
    payload_mestre = {
        "projeto_id": projeto_id,
        "usuario_id": str(usuario_id),
        "descricao": descricao,
        "data": dt_compra.strftime("%Y-%m-%d"),
        "data_vencimento": dt_compra.strftime("%Y-%m-%d"),
        "tipo": tipo,
        "valor_plan": 0.0,
        "valor_real": valor,
        "status": "Realizado",
        "cc_tipo": "LCL",
        "cc_qtd_parcelas": parcelas,
        "permite_parcial": permite_parcial,
    }

    if permite_parcial:
      payload_mestre["parcial_real"] = valor
      payload_mestre["parcial_data"] = dt_compra.strftime("%Y-%m-%d")

    if id_existente:
      supabase.table("lancamentos").update(payload_mestre).eq(
          "id", id_existente
      ).execute()
    else:
      supabase.table("lancamentos").insert(payload_mestre).execute()

    # Gerar parcelas sequenciais nas faturas
    for i in range(parcelas):
      v_parc = base_val + (residuo if i == (parcelas - 1) else 0.0)
      dt_venc_p = somar_meses_data(dt_1_venc, i + 1, dia_vencimento=venc)

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
          supabase, None, cartao, dt_venc_p, usuario_id
      )

    return f"✅ Compra **{descricao}** registrada no cartão **{cartao}** ({parcelas}x de R$ {base_val:.2f})!"

  # 3. CONVENCIONAL OU PARCIAL (SEM CARTÃO)
  if intencao == "PARCIAL" or permite_parcial:
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
        "permite_parcial": True,
    }).execute()
    return f"✅ Lançamento parcial de **R$ {valor:,.2f}** gravado!"

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
    supabase.table("lancamentos").insert({
        "projeto_id": projeto_id,
        "usuario_id": str(usuario_id),
        "descricao": descricao,
        "data": dt_venc,
        "data_vencimento": dt_venc,
        "tipo": tipo,
        "valor_plan": valor if status == "Planejado" else 0.0,
        "valor_real": valor if status == "Realizado" else 0.0,
        "status": status,
        "permite_parcial": permite_parcial,
    }).execute()
    return f"✅ Lançamento **{descricao}** salvo com sucesso!"


# ==============================================================================
# INTERFACE DA TELA DE CONCILIAÇÃO
# ==============================================================================


def exibir_conciliacao(
    df, supabase, ID_USUARIO_LOGADO, format_moeda, parse_moeda
):
  """Sub-rotina da Tela Conciliação."""
  st.markdown("""
        <style>
        div[data-testid="stColumn"] div.stButton > button {
            padding: 2px 4px !important;
            min-width: 32px !important;
            height: 28px !important;
            font-size: 11px !important;
            white-space: nowrap !important;
        }
        </style>
    """, unsafe_allow_html=True)

  if "reset_count" not in st.session_state:
    st.session_state.reset_count = 0

  reset_key = st.session_state.reset_count

  col_titulo, col_ajuda = st.columns([4, 1])

  with col_titulo:
    st.markdown(
        f'<div class="titulo-tela" style="margin-top:0px;">Conciliação:'
        f" {st.session_state.projeto_ativo}</div>",
        unsafe_allow_html=True,
    )

  with col_ajuda:
    st.markdown("""
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
        """, unsafe_allow_html=True)

    if st.button("AJUDA", type="primary", use_container_width=True):
      st.session_state["exibir_ajuda_conciliacao"] = not st.session_state.get(
          "exibir_ajuda_conciliacao", False
      )
      st.rerun()

  if st.session_state.get("exibir_ajuda_conciliacao", False):
    renderizar_ajuda_conciliacao()

  st.markdown("""
        <style>
        .block-container { padding-top: 2rem !important; }
        [data-testid="stWidgetLabel"] p { font-size: 0.85rem !important; white-space: nowrap !important; }
        .stMarkdown div p { margin-bottom: 0px !important; }
        hr { margin-top: 0.5rem !important; margin-bottom: 0.5rem !important; }
        </style>
    """, unsafe_allow_html=True)

  hoje_c = (datetime.utcnow() - timedelta(hours=3)).date()
  ini_mes_c = hoje_c.replace(day=1)
  limite_c = hoje_c - timedelta(days=4)

  col_aviso, col_tog = st.columns([4, 3])
  col_aviso.markdown(
      '<div style="font-size: 0.8rem; color: #555; margin-top: 10px;">📱🔄 SE'
      " USANDO O CELULAR, TRABALHE COM ELE NA HORIZONTAL</div>",
      unsafe_allow_html=True,
  )

  abrir_sem_plan = col_tog.toggle(
      "Lançar sem Planejamento",
      value=st.session_state.get("abrir_sem_plan", False),
  )
  st.session_state.abrir_sem_plan = abrir_sem_plan

  listar_todos_mes = col_tog.toggle(
      "Listar todos Lançamentos do mês",
      value=st.session_state.get("listar_todos_mes", False),
  )
  st.session_state.listar_todos_mes = listar_todos_mes

  st.divider()

  lista_cartoes_ccp = buscar_cartoes_lcp(df)

  # --- ÁREA: LANÇAR SEM PLANEJAMENTO ---
  if st.session_state.abrir_sem_plan:
    cols_sp = st.columns(
        [1.8, 0.8, 1.0, 1.3, 0.6, 0.5], vertical_alignment="center"
    )
    sp_desc = cols_sp[0].text_input(
        "Descrição", key=f"sp_desc_{reset_key}", placeholder="Ex: Combustível"
    )
    sp_tipo = cols_sp[1].selectbox(
        "E/S", ["Saída", "Entrada"], key=f"sp_tipo_{reset_key}"
    )
    sp_valor = cols_sp[2].text_input(
        "Valor Real", key=f"sp_valor_{reset_key}", value="0,00"
    )

    sp_cartao_sel = cols_sp[3].selectbox(
        "Cartão", lista_cartoes_ccp, key=f"sp_cartao_sel_{reset_key}"
    )
    sp_parc = cols_sp[4].number_input(
        "Parc.",
        min_value=0,
        max_value=12,
        value=0,
        step=1,
        key=f"sp_parc_{reset_key}",
    )

    sp_cartao_manual = ""
    if sp_cartao_sel == "+ Outro Cartão...":
      sp_cartao_manual = st.text_input(
          "Nome do Cartão",
          key=f"sp_cartao_manual_input_{reset_key}",
          placeholder="Ex: ITAÚ MASTER",
      )

    with cols_sp[5]:
      st.markdown(
          '<div style="margin-top: 28px;"></div>', unsafe_allow_html=True
      )
      btn_confirmar = st.button(
          "Ok", key=f"btn_sp_conf_{reset_key}", use_container_width=True
      )

    if btn_confirmar:
      v_sp = parse_moeda(sp_valor)
      if sp_desc and v_sp > 0:
        nome_cartao_final = (
            sp_cartao_manual.strip()
            if sp_cartao_sel == "+ Outro Cartão..."
            else sp_cartao_sel
        )

        dados_sp = {
            "projeto_id": st.session_state.projeto_ativo,
            "descricao": sp_desc,
            "valor": v_sp,
            "tipo": sp_tipo,
            "data_vencimento": hoje_c.strftime("%Y-%m-%d"),
            "cartao": nome_cartao_final,
            "parcelas": int(sp_parc),
            "intencao": "REALIZAR",
            "permite_parcial": False,
        }

        salvar_lancamento_oficial(supabase, ID_USUARIO_LOGADO, dados_sp)
        st.session_state.reset_count += 1
        st.session_state.abrir_sem_plan = False
        st.rerun()

    st.divider()

  df_c = df.copy() if df is not None else pd.DataFrame()
  if not df_c.empty:
    df_c["dt_obj"] = pd.to_datetime(df_c["data"]).dt.date
    df_c["parcial_real"] = pd.to_numeric(
        df_c["parcial_real"], errors="coerce"
    ).fillna(0)

    df_base_tela = df_c[
        (df_c["parcial_real"] == 0)
        & (
            ~df_c["cc_tipo"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .str.contains(r"LCL|\$CCL", regex=True)
        )
    ].copy()

    if st.session_state.listar_todos_mes:
      proximo_mes = (ini_mes_c + timedelta(days=32)).replace(day=1)
      fim_mes_c = proximo_mes - timedelta(days=1)
      df_f = df_base_tela[
          (df_base_tela["dt_obj"] >= ini_mes_c)
          & (df_base_tela["dt_obj"] <= fim_mes_c)
      ].copy()
    else:
      df_f = df_base_tela[
          (df_base_tela["dt_obj"] >= ini_mes_c)
          & (df_base_tela["dt_obj"] <= hoje_c)
          & (
              (df_base_tela["status"].isin(["Planejado", "PLAN"]))
              | (
                  (df_base_tela["status"].isin(["Realizado", "REAL"]))
                  & (df_base_tela["dt_obj"] >= limite_c)
              )
              | (
                  (df_base_tela["valor_plan"] == 0)
                  & (df_base_tela["valor_real"] > 0)
              )
          )
      ].copy()

    parciais_topo = df_f[
        (df_f["permite_parcial"] == True) & (df_f["dt_obj"] >= ini_mes_c)
    ]
    demais_itens = df_f[~df_f.index.isin(parciais_topo.index)].sort_values(
        "dt_obj", ascending=False
    )
    df_final_concilia = pd.concat([parciais_topo, demais_itens])

    h1, h2, h3, h4, h5, h6, h7, h8 = st.columns(
        [2.2, 0.4, 0.9, 0.9, 0.9, 1.2, 0.5, 0.7], vertical_alignment="center"
    )
    h1.write("**Data - Descrição**")
    h2.write("**E/S**")
    h3.write("**V. Plan.**")
    h4.write("**V. Real**")
    h5.write("**V. Parcial**")
    h6.write("**Cartão**")
    h7.write("**Parc.**")
    h8.write("**Ação**")
    st.divider()

    for _, row in df_final_concilia.iterrows():
      v_acumulado_desc = (
          df[df["descricao"] == row["descricao"]]["parcial_real"]
          .fillna(0)
          .sum()
      )
      cor_txt = (
          "red"
          if (row["valor_plan"] > 0 and v_acumulado_desc > row["valor_plan"])
          else "black"
      )

      st.markdown(
          '<div style="margin-bottom: -32px;"></div>', unsafe_allow_html=True
      )

      c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(
          [2.2, 0.4, 0.9, 0.9, 0.9, 1.2, 0.5, 0.7], vertical_alignment="center"
      )

      c1.markdown(
          f"<span style='color:{cor_txt}; font-weight:"
          f" 500;'>{row['dt_obj'].strftime('%d/%m/%Y')} -"
          f" {row['descricao']}</span>",
          unsafe_allow_html=True,
      )
      cor_tipo = "red" if row["tipo"] == "Saída" else "blue"
      c2.markdown(
          f"<span style='color:{cor_tipo}'>{row['tipo'][0]}</span>",
          unsafe_allow_html=True,
      )

      valor_exibicao_real = row["valor_real"]
      if str(row.get("cc_tipo")).strip().upper() in [
          "$CCP",
          "CCP",
          "'Z $CCP",
          "Z|$CCP",
      ]:
        soma_lcls = df[
            (
                df["cc_tipo"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
                .str.contains(r"LCL|\$CCL", regex=True)
            )
            & (
                df["descricao"].fillna("").astype(str).str.strip().str.upper()
                == str(row["descricao"]).strip().upper()
            )
            & (
                pd.to_datetime(df["data_vencimento"]).dt.month
                == row["dt_obj"].month
            )
            & (
                pd.to_datetime(df["data_vencimento"]).dt.year
                == row["dt_obj"].year
            )
        ]["valor_real"].sum()
        valor_exibicao_real = soma_lcls

      if row["permite_parcial"]:
        c3.markdown(
            f"<span style='color:{cor_txt}'>{format_moeda(row['valor_plan'])}</span>",
            unsafe_allow_html=True,
        )
        c4.markdown(
            f"<span style='color:{cor_txt}'>{format_moeda(v_acumulado_desc)}</span>",
            unsafe_allow_html=True,
        )

        v_key = f"v_p_{row['id']}"
        if v_key not in st.session_state:
          st.session_state[v_key] = 0

        v_parc_in = c5.text_input(
            "",
            key=f"p_{row['id']}_{reset_key}_{st.session_state[v_key]}",
            value="0,00",
            label_visibility="collapsed",
        )

        cc_sel = c6.selectbox(
            "",
            lista_cartoes_ccp,
            key=f"cc_p_sel_{row['id']}_{reset_key}",
            label_visibility="collapsed",
        )
        qtd_parc_in = c7.number_input(
            "",
            min_value=0,
            max_value=12,
            value=0,
            step=1,
            key=f"q_p_{row['id']}_{reset_key}",
            label_visibility="collapsed",
        )

        cc_outro_nome = ""
        if cc_sel == "+ Outro Cartão...":
          cc_outro_nome = st.text_input(
              "Digite o Cartão",
              key=f"cc_outro_p_{row['id']}_{reset_key}",
              placeholder="Ex: ITAÚ MASTER",
          )

        if c8.button("Ok", key=f"btn_p_{row['id']}", use_container_width=True):
          v_dig = parse_moeda(v_parc_in)
          if v_dig > 0:
            nome_cartao_final = (
                cc_outro_nome.strip()
                if cc_sel == "+ Outro Cartão..."
                else cc_sel
            )

            dados_p = {
                "projeto_id": st.session_state.projeto_ativo,
                "descricao": row["descricao"],
                "valor": v_dig,
                "tipo": row["tipo"],
                "data_vencimento": hoje_c.strftime("%Y-%m-%d"),
                "cartao": nome_cartao_final,
                "parcelas": int(qtd_parc_in),
                "intencao": "PARCIAL",
                "permite_parcial": True,
            }

            salvar_lancamento_oficial(supabase, ID_USUARIO_LOGADO, dados_p)
            st.session_state.reset_count += 1
            st.session_state[v_key] += 1
            st.rerun()

      else:
        c3.write(format_moeda(row["valor_plan"]))
        if row["status"] in ["Realizado", "REAL"]:
          c4.write(format_moeda(valor_exibicao_real))
          c5.write("-")
          c6.write("-")
          c7.write("-")
          c8.write("✅")
        else:
          v_norm_in = c4.text_input(
              "",
              key=f"n_{row['id']}_{reset_key}",
              value="0,00",
              label_visibility="collapsed",
          )
          c5.write("-")

          cc_norm_sel = c6.selectbox(
              "",
              lista_cartoes_ccp,
              key=f"cc_n_sel_{row['id']}_{reset_key}",
              label_visibility="collapsed",
          )
          qtd_norm_in = c7.number_input(
              "",
              min_value=0,
              max_value=12,
              value=0,
              step=1,
              key=f"q_n_{row['id']}_{reset_key}",
              label_visibility="collapsed",
          )

          cc_norm_outro_nome = ""
          if cc_norm_sel == "+ Outro Cartão...":
            cc_norm_outro_nome = st.text_input(
                "Digite o Cartão",
                key=f"cc_outro_n_{row['id']}_{reset_key}",
                placeholder="Ex: ITAÚ MASTER",
            )

          if c8.button(
              "Ok", key=f"btn_n_{row['id']}", use_container_width=True
          ):
            v_para_gravar = parse_moeda(v_norm_in)
            if v_para_gravar == 0:
              v_para_gravar = row["valor_plan"]

            nome_cartao_final = (
                cc_norm_outro_nome.strip()
                if cc_norm_sel == "+ Outro Cartão..."
                else cc_norm_sel
            )

            is_cc = (
                bool(nome_cartao_final)
                and nome_cartao_final != "Nenhum"
                and int(qtd_norm_in) > 0
            )

            if is_cc:
              dados_c = {
                  "projeto_id": st.session_state.projeto_ativo,
                  "descricao": row["descricao"],
                  "valor": v_para_gravar,
                  "tipo": row["tipo"],
                  "data_vencimento": row["dt_obj"].strftime("%Y-%m-%d"),
                  "cartao": nome_cartao_final,
                  "parcelas": int(qtd_norm_in),
                  "intencao": "REALIZAR",
                  "id_existente": row["id"],
                  "permite_parcial": False,
              }
              salvar_lancamento_oficial(supabase, ID_USUARIO_LOGADO, dados_c)
            else:
              supabase.table("lancamentos").update({
                  "valor_real": float(v_para_gravar),
                  "status": "Realizado",
              }).eq("id", row["id"]).execute()

            st.session_state.reset_count += 1
            st.rerun()

      st.divider()
  else:
    st.info("Nenhum lançamento pendente para conciliação.")