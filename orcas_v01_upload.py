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

def render_upload(usuario_id=None, projeto_id=None):
    st.subheader("📤 Importar Lançamentos via Excel")
    
    # Mensagem amigável e clara para o usuário
    st.write(
        "Faça o envio da sua planilha Excel (`.xlsx`) no formato padrão. "
        "Lançamentos novos serão **cadastrados automaticamente**, e aqueles que já possuem **ID** "
        "serão **atualizados** no sistema."
    )

    # --- RESOLUÇÃO FLEXÍVEL DAS CHAVES DE SESSÃO ---
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
        st.error("⚠️ Usuário ou Projeto Ativo não identificados na sessão. Efetue o login novamente.")
        return

    st.info(f"📌 **Vinculará os dados importados a:** Usuário `{usr_id}` | Projeto `{proj_id}`")

    uploaded_file = st.file_uploader("Selecione a planilha Excel", type=["xlsx"])

    if uploaded_file is not None:
        if st.button("Iniciar Upload para o Supabase", type="primary", use_container_width=True):
            with st.spinner("Lendo e tratando dados da planilha..."):
                try:
                    df = pd.read_excel(uploaded_file, engine="openpyxl")

                    if df.empty:
                        st.warning("A planilha enviada está vazia.")
                        return

                    # Formata datas para o padrão aceito pelo banco (AAAA-MM-DD)
                    for col in ["data_vencimento", "data", "parcial_data"]:
                        if col in df.columns:
                            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

                    records = []
                    for _, row in df.iterrows():
                        item = {}
                        for col in df.columns:
                            val = sanitize_val(row[col])
                            
                            # Trata booleanos
                            if col in ["realizado", "recorrente", "permite_parcial", "usar_media"]:
                                if val is not None:
                                    val = bool(val)
                            
                            # Ignora ID nulo para usar a sequência automática do banco de dados
                            if col == "id" and val is None:
                                continue
                                
                            item[col] = val

                        # --- FORÇA O PERTENCIMENTO AO USUÁRIO E PROJETO ATIVO ---
                        item["usuario_id"] = usr_id
                        item["projeto_id"] = proj_id

                        records.append(item)

                    # Envio em lotes (Batches)
                    progress_bar = st.progress(0)
                    total = len(records)
                    uploaded_count = 0

                    for i in range(0, total, BATCH_SIZE):
                        batch = records[i:i + BATCH_SIZE]
                        supabase.table("lancamentos").upsert(batch).execute()
                        uploaded_count += len(batch)
                        progress_bar.progress(uploaded_count / total)

                    st.success(f"✅ Upload concluído! {total} registro(s) processado(s) com sucesso.")
                except Exception as e:
                    st.error(f"Erro durante o upload: {e}")