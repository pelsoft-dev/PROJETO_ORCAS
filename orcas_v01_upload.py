import math
import pandas as pd
import streamlit as st
from orcas_v01_security import supabase

BATCH_SIZE = 100

def sanitize_val(val):
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    return val

def render_upload():
    st.subheader("📤 Importar Lançamentos via Excel")
    st.info("Envie um arquivo `.xlsx` com a estrutura padrão. Registros com `id` existente serão atualizados (Upsert); sem `id`, serão inseridos.")

    uploaded_file = st.file_uploader("Selecione a planilha Excel", type=["xlsx"])

    if uploaded_file is not None:
        if st.button("Iniciar Upload para o Supabase"):
            with st.spinner("Lendo e tratando dados da planilha..."):
                try:
                    df = pd.read_excel(uploaded_file, engine="openpyxl")

                    if df.empty:
                        st.warning("A planilha enviada está vazia.")
                        return

                    # Formata datas
                    for col in ["data_vencimento", "data", "parcial_data"]:
                        if col in df.columns:
                            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

                    records = []
                    for _, row in df.iterrows():
                        item = {}
                        for col in df.columns:
                            val = sanitize_val(row[col])
                            if col in ["realizado", "recorrente", "permite_parcial", "usar_media"]:
                                if val is not None:
                                    val = bool(val)
                            if col == "id" and val is None:
                                continue
                            item[col] = val
                        records.append(item)

                    # Envio em lotes
                    progress_bar = st.progress(0)
                    total = len(records)
                    uploaded_count = 0

                    for i in range(0, total, BATCH_SIZE):
                        batch = records[i:i + BATCH_SIZE]
                        supabase.table("lancamentos").upsert(batch).execute()
                        uploaded_count += len(batch)
                        progress_bar.progress(uploaded_count / total)

                    st.success(f"✅ Upload concluído! {total} registros processados.")
                except Exception as e:
                    st.error(f"Erro durante o upload: {e}")