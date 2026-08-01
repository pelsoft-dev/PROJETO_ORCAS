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

    # --- SELEÇÃO DAS REGRAS DE IMPORTAÇÃO (RADIO BUTTONS SEM PADRÃO) ---
    st.markdown("### Selecione o modo de importação:")
    modo_importacao = st.radio(
        "Escolha como o sistema deve tratar os dados da planilha em relação ao banco de dados:",
        options=[
            "Apague todos os dados do DB e suba todo o conteúdo da planilha",
            "Lançamentos novos serão cadastrados, e os já existentes serão atualizados",
            "Suba todos os Lançamentos e seus Planejamentos, mas zere todos os Realizados"
        ],
        index=None,
        key="modo_importacao_radio"
    )

    if not modo_importacao:
        st.warning("⚠️ Selecione um modo de importação acima para habilitar o envio do arquivo.")
        return

    uploaded_file = st.file_uploader("Selecione a planilha Excel (.xlsx)", type=["xlsx"])

    if uploaded_file is not None:
        if st.button("Iniciar Upload para o Supabase", type="primary", use_container_width=True):
            with st.spinner("Lendo e tratando dados da planilha..."):
                try:
                    df = pd.read_excel(uploaded_file, engine="openpyxl")

                    if df.empty:
                        st.warning("A planilha enviada está vazia.")
                        return

                    # MODO 1: Deletar dados antigos do usuário + projeto antes da gravação
                    if modo_importacao == "Apague todos os dados do DB e suba todo o conteúdo da planilha":
                        st.toast("Limpando lançamentos anteriores do projeto...", icon="🗑️")
                        supabase.table("lancamentos") \
                            .delete() \
                            .eq("usuario_id", usr_id) \
                            .eq("projeto_id", proj_id) \
                            .execute()

                    # Formata colunas de datas para YYYY-MM-DD
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
                            
                            # Ignora ID nulo (ou quando for limpeza total) para usar a sequence automática
                            if col == "id" and (val is None or modo_importacao == "Apague todos os dados do DB e suba todo o conteúdo da planilha"):
                                continue
                                
                            item[col] = val

                        # MODO 3: Zerar Realizados na Importação
                        if modo_importacao == "Suba todos os Lançamentos e seus Planejamentos, mas zere todos os Realizados":
                            item["realizado"] = False
                            item["valor_realizado"] = 0.0
                            item["valor_real"] = 0.0
                            item["parcial_real"] = 0.0

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

                    st.success(f"✅ Upload concluído com sucesso! {total} registro(s) processado(s).")
                except Exception as e:
                    st.error(f"Erro durante o upload: {e}")