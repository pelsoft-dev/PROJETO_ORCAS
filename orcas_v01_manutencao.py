from datetime import datetime
import pandas as pd
import streamlit as st


def obter_limites_projeto(supabase, projeto_id):
  """Busca os limites de data cadastrados para o projeto ativo."""
  dt_ini_def = datetime.today().date().replace(day=1)
  dt_fim_def = datetime(datetime.today().year, 12, 31).date()

  if not projeto_id:
    return dt_ini_def, dt_fim_def

  try:
    res = (
        supabase.table("config_projetos")
        .select("data_ini, data_fim")
        .eq("projeto_id", str(projeto_id))
        .execute()
    )
    if res and res.data:
      dados = res.data[0]
      if dados.get("data_ini"):
        dt_ini_def = datetime.strptime(
            str(dados["data_ini"])[:10], "%Y-%m-%d"
        ).date()
      if dados.get("data_fim"):
        dt_fim_def = datetime.strptime(
            str(dados["data_fim"])[:10], "%Y-%m-%d"
        ).date()
  except Exception as e:
    print(f"Erro ao buscar datas limite do projeto: {e}")

  return dt_ini_def, dt_fim_def


def aplicar_filtro_argumento(query, campo_db, argumento, conteudo):
  """Aplica os operadores de filtro do Supabase de acordo com a regra escolhida."""
  texto = str(conteudo).strip()
  if not texto:
    return query

  if argumento == "igual a":
    return query.ilike(campo_db, texto)
  elif argumento == "que comece com":
    return query.ilike(campo_db, f"{texto}%")
  elif argumento == "que contenha":
    return query.ilike(campo_db, f"%{texto}%")
  elif argumento == "que termine com":
    return query.ilike(campo_db, f"%{texto}")
  return query


def ajustar_dia_vencimento(data_str, novo_dia):
  """Ajusta o dia de uma data 'YYYY-MM-DD' mantendo o ano e mês."""
  try:
    dt = datetime.strptime(str(data_str)[:10], "%Y-%m-%d")
    # Trata caso o mês não tenha o dia desejado (ex: dia 31 em fevereiro)
    import calendar

    _, ultimo_dia = calendar.monthrange(dt.year, dt.month)
    dia_final = min(int(novo_dia), ultimo_dia)
    dt_nova = dt.replace(day=dia_final)
    return dt_nova.strftime("%Y-%m-%d")
  except Exception:
    return data_str


def renderizar_pagina_manutencao(supabase, usuario_id, projeto_ativo):
  st.markdown("### 🛠️ Manutenção em Lote de Dados")
  st.caption(
      "Realize alterações ou exclusões massivas com base em regras de filtro"
      f" para o projeto **{projeto_ativo}**."
  )

  dt_ini_padrao, dt_fim_padrao = obter_limites_projeto(supabase, projeto_ativo)

  # --- CONSTRUÇÃO DO PAINEL DE REGRAS ---
  st.markdown("#### 📐 Definir Regra de Operação")

  c_acao, c_sobre, c_de, c_ate = st.columns([1.5, 2, 2, 2])
  with c_acao:
    acao = st.selectbox(
        "AÇÃO", ["alterar", "excluir"], key="manut_acao", help="Operação no banco"
    )

  with c_sobre:
    sobre_quem = st.selectbox(
        "SOBRE QUEM",
        ["lançamentos", "parciais", "cartão de crédito"],
        key="manut_sobre",
    )

  with c_de:
    dt_de = st.date_input(
        "DE", value=dt_ini_padrao, format="DD/MM/YYYY", key="manut_de"
    )

  with c_ate:
    dt_ate = st.date_input(
        "ATÉ", value=dt_fim_padrao, format="DD/MM/YYYY", key="manut_ate"
    )

  c_arg, c_cont, c_campo, c_para = st.columns([2, 3, 2.5, 2.5])
  with c_arg:
    argumento = st.selectbox(
        "ARGUMENTO (Descrição)",
        ["que contenha", "igual a", "que comece com", "que termine com"],
        key="manut_arg",
    )

  with c_cont:
    conteudo = st.text_input(
        "CONTEÚDO DA DESCRIÇÃO",
        placeholder="Ex: curso de inglês",
        key="manut_conteudo",
    )

  # Mapeamento correto com as colunas reais do schema Supabase
  campos_mapeados = {
      "Data de Vencimento": "data_vencimento",
      "Valor Planejado": "valor_planejado",
      "Valor Realizado": "valor_realizado",
      "Dia de Vencimento": "dia_mes",
      "Descrição": "descricao",
  }

  if sobre_quem == "cartão de crédito":
    campos_mapeados["Dia de Corte"] = "dia_corte"
    campos_mapeados["Nome Cartão"] = "cartao"

  with c_campo:
    if acao == "alterar":
      campo_label = st.selectbox(
          "CAMPO A ALTERAR", list(campos_mapeados.keys()), key="manut_campo"
      )
      campo_db = campos_mapeados[campo_label]
    else:
      st.text_input(
          "CAMPO",
          value="[Toda a linha]",
          disabled=True,
          help="Exclusão remove o registro completo.",
      )
      campo_db = None

  with c_para:
    novo_valor = None
    if acao == "alterar":
      if "Data de Vencimento" in campo_label:
        novo_valor = st.date_input(
            "PARA (Nova Data)",
            value=datetime.today().date(),
            format="DD/MM/YYYY",
            key="manut_para_dt",
        )
      elif "Valor" in campo_label:
        novo_valor = st.number_input(
            "PARA (Novo Valor)",
            value=0.0,
            format="%.2f",
            key="manut_para_num",
        )
      elif "Dia" in campo_label:
        novo_valor = st.number_input(
            "PARA (Novo Dia)",
            min_value=1,
            max_value=31,
            value=1,
            key="manut_para_dia",
        )
      else:
        novo_valor = st.text_input(
            "PARA (Novo Texto)", key="manut_para_txt"
        )
    else:
      st.text_input("PARA", value="N/A", disabled=True)

  st.markdown("---")

  # --- ETAPA 1: BUSCA E PRÉ-VISUALIZAÇÃO ---
  b_filtrar, _ = st.columns([2, 6])
  executar_busca = b_filtrar.button(
      "🔍 Pré-visualizar Registros Afetados",
      type="secondary",
      use_container_width=True,
  )

  if (
      executar_busca
      or st.session_state.get("manut_preview_ativa")
      or "df_preview_manut" in st.session_state
  ):
    if executar_busca:
      st.session_state["manut_preview_ativa"] = True

      query = (
          supabase.table("lancamentos")
          .select("*")
          .eq("usuario_id", str(usuario_id))
          .eq("projeto_id", str(projeto_ativo))
      )

      if dt_de:
        query = query.gte("data_vencimento", str(dt_de))
      if dt_ate:
        query = query.lte("data_vencimento", str(dt_ate))

      if sobre_quem == "parciais":
        query = query.eq("permite_parcial", True)
      elif sobre_quem == "cartão de crédito":
        query = query.not_.is_("cartao", "null")

      if conteudo:
        query = aplicar_filtro_argumento(
            query, "descricao", argumento, conteudo
        )

      res = query.execute()
      df_result = pd.DataFrame(res.data) if res and res.data else pd.DataFrame()
      st.session_state["df_preview_manut"] = df_result

    df_preview = st.session_state.get("df_preview_manut", pd.DataFrame())

    if df_preview.empty:
      st.warning(
          "⚠️ Nenhum registro foi encontrado para os critérios selecionados."
      )
    else:
      st.success(f"🎯 **{len(df_preview)}** registro(s) localizados para a ação.")
      st.dataframe(df_preview, use_container_width=True, hide_index=True)

      # --- ETAPA 2: EXECUÇÃO DA MANUTENÇÃO ---
      st.markdown("#### 🚨 Confirmar Operação em Lote")

      if acao == "alterar":
        msg_confirm = f"Confirma ALTERAR o campo **{campo_label}** para **'{novo_valor}'** em {len(df_preview)} registros?"
      else:
        msg_confirm = (
            f"Confirma **EXCLUIR DEFINITIVAMENTE** {len(df_preview)} registros"
            " do banco de dados?"
        )

      st.warning(msg_confirm)

      col_conf1, col_conf2 = st.columns([2, 6])
      btn_executar = col_conf1.button(
          "🔥 Confirmar e Executar", type="primary", use_container_width=True
      )

      if btn_executar:
        ids_afetados = df_preview["id"].tolist()

        try:
          if acao == "alterar":
            # Trata alteração do Dia de Vencimento
            if campo_label == "Dia de Vencimento":
              novo_dia_str = str(int(novo_valor))
              for idx, row in df_preview.iterrows():
                id_reg = row["id"]
                dt_atual = row.get("data_vencimento")
                dt_nova = (
                    ajustar_dia_vencimento(dt_atual, novo_dia_str)
                    if dt_atual
                    else None
                )

                payload = {"dia_mes": novo_dia_str}
                if dt_nova:
                  payload["data_vencimento"] = dt_nova

                supabase.table("lancamentos").update(payload).eq(
                    "id", id_reg
                ).execute()

            else:
              val_salvar = (
                  str(novo_valor)
                  if isinstance(novo_valor, datetime)
                  else novo_valor
              )
              supabase.table("lancamentos").update({campo_db: val_salvar}).in_(
                  "id", ids_afetados
              ).execute()

            st.success(
                f"✅ Sucesso! {len(ids_afetados)} registros foram alterados."
            )

          elif acao == "excluir":
            supabase.table("lancamentos").delete().in_(
                "id", ids_afetados
            ).execute()
            st.success(
                f"🗑️ Sucesso! {len(ids_afetados)} registros foram excluídos."
            )

          if "df_preview_manut" in st.session_state:
            del st.session_state["df_preview_manut"]
          st.session_state["manut_preview_ativa"] = False
          st.rerun()

        except Exception as err:
          st.error(f"❌ Erro ao executar manutenção no banco: {err}")