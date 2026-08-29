import math
import pandas as pd
import streamlit as st
from orcas_v01_security import supabase

BATCH_SIZE = 100

# Ordem exata das colunas da planilha (conforme anexo01)
ORDEM_COLUNAS_EXCEL = [
    "descricao",            # Coluna A (1)
    "valor",                # Coluna B (2)
    "tipo",                 # Coluna C (3)
    "data_vencimento",      # Coluna D (4)
    "realizado",            # Coluna E (5)
    "valor_realizado",      # Coluna F (6)
    "categoria",            # Coluna G (7)
    "recorrente",           # Coluna H (8)
    "valor_plan",           # Coluna I (9)
    "valor_real",           # Coluna J (10)
    "status",               # Coluna K (11)
    "data",                 # Coluna L (12)
    "permite_parcial",      # Coluna M (13)
    "usar_media",           # Coluna N (14)
    "complemento_tipo",     # Coluna O (15)
    "complemento_texto",    # Coluna P (16)
    "correcao_freq",        # Coluna Q (17)
    "correcao_valor",       # Coluna R (18)
    "id_pai",               # Coluna S (19)
    "parcial_real",         # Coluna T (20)
    "parcial_data",         # Coluna U (21)
    "regra_parcial",        # Coluna V (22)
    "cc_tipo",              # Coluna W (23)
    "cc_dia_corte",         # Coluna X (24)
    "cc_qtd_parcelas",      # Coluna Y (25)
    "cc_descricao",         # Coluna Z (26)
    "cc_data_compra",       # Coluna AA (27)
]

COLUNAS_VALIDAS_BANCO = {
    "usuario_id",
    "projeto_id",
    "descricao",
    "complemento",
    "categoria",
    "tipo",
    "valor",
    "valor_plan",
    "valor_real",
    "valor_realizado",
    "data_vencimento",
    "data",
    "realizado",
    "recorrente",
    "permite_parcial",
    "usar_media",
    "observacao",
    "parcial_real",
    "parcial_data",
    "status",
}


def sanitize_val(val):
  if pd.isna(val) or val is None:
    return None
  if isinstance(val, float) and math.isnan(val):
    return None
  return val


def parse_float_val(val):
  val_clean = sanitize_val(val)
  if val_clean is None:
    return 0.0
  if isinstance(val_clean, (int, float)):
    return float(val_clean)

  val_str = str(val_clean).strip()
  if not val_str:
    return 0.0

  try:
    val_str = val_str.replace(".", "").replace(",", ".")
    return float(val_str)
  except ValueError:
    return 0.0


def render_upload(usuario_id=None, projeto_id=None):
  st.subheader("📤 Importar Lançamentos via Excel")

  usr_id = (
      usuario_id
      or st.session_state.get("user_id")
      or st.session_state.get("usuario_id")
      or st.session_state.get("usuario")
  )
  proj_id = (
      projeto_id
      or st.session_state.get("projeto_ativo")
      or st.session_state.get("projeto")
      or st.session_state.get("plano_ativo")
  )

  if not usr_id or not proj_id:
    st.error(
        "⚠️ Usuário ou Projeto Ativo não identificados na sessão. Efetue o"
        " login novamente."
    )
    return

  st.info(
      f"📌 **Vinculará os dados importados a:** Usuário `{usr_id}` | Projeto"
      f" `{proj_id}`"
  )

  st.markdown("### Selecione o modo de importação:")
  modo_importacao = st.radio(
      "Escolha como o sistema deve tratar os dados da planilha em relação ao"
      " banco de dados:",
      options=[
          "Apague todos os dados do DB e suba todo o conteúdo da planilha",
          (
              "Suba todos os Lançamentos e seus Planejamentos, mas zere todos"
              " os Realizados"
          ),
      ],
      index=None,
      key="modo_importacao_radio",
  )

  if not modo_importacao:
    st.warning(
        "⚠️ Selecione um modo de importação acima para habilitar o envio do"
        " arquivo."
    )
    return

  uploaded_file = st.file_uploader(
      "Selecione a planilha Excel (.xlsx)", type=["xlsx"]
  )

  if uploaded_file is not None:
    if st.button(
        "Iniciar Upload para o Supabase",
        type="primary",
        use_container_width=True,
    ):
      with st.spinner("Lendo e tratando dados da planilha..."):
        try:
          # Leitura inicial das duas primeiras células da linha 1 para verificação
          df_check = pd.read_excel(uploaded_file, nrows=1, header=None, engine="openpyxl")
          
          candidato_a1 = str(df_check.iloc[0, 0]).strip().lower() if df_check.shape[1] > 0 else ""
          candidato_b1 = str(df_check.iloc[0, 1]).strip().lower() if df_check.shape[1] > 1 else ""

          # Valida se possui a linha de cabeçalho exata (A1 == "descricao" e B1 == "valor")
          tem_cabecalho = (candidato_a1 == "descricao") and (candidato_b1 == "valor")

          if tem_cabecalho:
            df = pd.read_excel(uploaded_file, engine="openpyxl")
          else:
            # Sem cabeçalho: lê sem header e atribui as colunas conforme o anexo01
            df = pd.read_excel(uploaded_file, header=None, engine="openpyxl")
            novas_colunas = {
                i: ORDEM_COLUNAS_EXCEL[i]
                for i in range(min(len(df.columns), len(ORDEM_COLUNAS_EXCEL)))
            }
            df.rename(columns=novas_colunas, inplace=True)

          if df.empty:
            st.warning("A planilha enviada está vazia.")
            return

          # Limpa os lançamentos anteriores do projeto
          st.toast("Limpando lançamentos anteriores do projeto...", icon="🗑️")
          supabase.table("lancamentos").delete().eq(
              "usuario_id", usr_id
          ).eq("projeto_id", proj_id).execute()

          # Formatação prévia de datas
          for col in ["data_vencimento", "data", "parcial_data"]:
            if col in df.columns:
              df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime(
                  "%Y-%m-%d"
              )

          records = []
          for _, row in df.iterrows():
            # VERIFICAÇÃO DE PARADA: Ao encontrar a primeira célula A (descricao) nula/vazia, encerra o programa
            desc_val = sanitize_val(row.get("descricao"))
            if desc_val is None or str(desc_val).strip() == "":
              break

            parcial_real = parse_float_val(row.get("parcial_real"))

            # OPÇÃO 2: Se tiver parcial_real > 0, descarta o lançamento
            if (
                modo_importacao
                == "Suba todos os Lançamentos e seus Planejamentos, mas zere"
                " todos os Realizados"
            ):
              if parcial_real > 0:
                continue

            item = {}
            item["descricao"] = str(desc_val).strip()

            # Trata 'complemento' unindo os campos de complemento se existirem
            comp_texto = sanitize_val(row.get("complemento_texto"))
            comp_orig = sanitize_val(row.get("complemento"))
            if comp_texto is not None:
              item["complemento"] = str(comp_texto).strip()
            elif comp_orig is not None:
              item["complemento"] = str(comp_orig).strip()

            # Leitura de Valores
            val_orig = parse_float_val(row.get("valor"))
            val_plan = row.get("valor_plan")
            val_real = row.get("valor_real")
            val_realizado = row.get("valor_realizado")

            final_plan = (
                parse_float_val(val_plan)
                if sanitize_val(val_plan) is not None
                else val_orig
            )
            raw_real = (
                val_real
                if sanitize_val(val_real) is not None
                else val_realizado
            )
            final_real = (
                parse_float_val(raw_real)
                if sanitize_val(raw_real) is not None
                else parcial_real
            )

            item["valor_plan"] = final_plan
            item["valor_real"] = final_real

            # Copia colunas válidas da planilha para o objeto final do banco
            for col in df.columns:
              if col in COLUNAS_VALIDAS_BANCO and col not in [
                  "valor_plan",
                  "valor_real",
                  "descricao",
                  "complemento",
              ]:
                val = sanitize_val(row[col])

                if col in [
                    "realizado",
                    "recorrente",
                    "permite_parcial",
                    "usar_media",
                ]:
                  if val is not None:
                    val = bool(val)

                item[col] = val

            # APLICAÇÃO ESTRITA DA OPÇÃO 2 (ZERAR REALIZADOS)
            if (
                modo_importacao
                == "Suba todos os Lançamentos e seus Planejamentos, mas zere"
                " todos os Realizados"
            ):
              item["valor_real"] = 0.0
              item["parcial_real"] = 0.0
              item["realizado"] = False
              item["status"] = "Planejado"

            item["usuario_id"] = usr_id
            item["projeto_id"] = proj_id

            # Remove ID se porventura vier na planilha
            item.pop("id", None)

            records.append(item)

          total = len(records)
          if total == 0:
            st.warning(
                "Nenhum lançamento válido para importar após a filtragem."
            )
            return

          # Envio em lotes para o Supabase
          progress_bar = st.progress(0)
          uploaded_count = 0

          for i in range(0, total, BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            supabase.table("lancamentos").insert(batch).execute()
            uploaded_count += len(batch)
            progress_bar.progress(uploaded_count / total)

          # MENSAGEM FINAL AJUSTADA
          st.success(
              f"✅ Upload concluído! Total de linhas do Excel que subiram para o"
              f" ORCAS = {total}"
          )
        except Exception as e:
          st.error(f"Erro durante o upload: {e}")