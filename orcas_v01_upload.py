import math
import pandas as pd
import streamlit as st
from orcas_v01_security import supabase

BATCH_SIZE = 100

# Colunas oficiais da tabela 'lancamentos' no Supabase
COLUNAS_VALIDAS_BANCO = {
    "usuario_id",
    "projeto_id",
    "descricao",
    "complemento",
    "categoria",
    "tipo",
    "valor",
    "data_vencimento",
    "data",
    "realizado",
    "valor_realizado",
    "recorrente",
    "permite_parcial",
    "usar_media",
    "observacao"
}

def sanitize_val(val):
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    return val

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
        st.error("⚠️ Usuário ou Projeto Ativo não identificados na sessão. Efetue o login novamente.")
        return

    st.info(f"📌 **Vinculará os dados importados a:** Usuário `{usr_id}` | Projeto `{proj_id}`")

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

                    # Limpa registros antigos se a opção 1 for escolhida
                    if modo_importacao == "Apague todos os dados do DB e suba todo o conteúdo da planilha":
                        st.toast("Limpando lançamentos anteriores do projeto...", icon="🗑️")
                        supabase.table("lancamentos") \
                            .delete() \
                            .eq("usuario_id", usr_id) \
                            .eq("projeto_id", proj_id) \
                            .execute()

                    # Formatação de datas
                    for col in ["data_vencimento", "data", "parcial_data"]:
                        if col in df.columns:
                            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

                    records = []
                    for _, row in df.iterrows():
                        item = {}

                        # --- TRATAMENTO E MIGRAÇÃO DAS COLUNAS DE VALOR (LEGAIS -> ATUAIS) ---
                        val_original = sanitize_val(row.get("valor"))
                        val_plan = sanitize_val(row.get("valor_plan"))
                        val_real = sanitize_val(row.get("valor_real"))
                        val_realizado_orig = sanitize_val(row.get("valor_realizado"))
                        parcial_real = sanitize_val(row.get("parcial_real"))

                        # 1. Define o valor planejado (se 'valor' estiver vazio, usa 'valor_plan')
                        valor_final = val_original if val_original is not None else val_plan
                        if valor_final is None:
                            valor_final = 0.0

                        # 2. Define o valor realizado (prioriza 'valor_realizado', 'valor_real' ou 'parcial_real')
                        realizado_final = val_realizado_orig
                        if realizado_final is None:
                            realizado_final = val_real if val_real is not None else parcial_real
                        if realizado_final is None:
                            realizado_final = 0.0

                        # Preenche os campos oficiais
                        item["valor"] = float(valor_final)
                        item["valor_realizado"] = float(realizado_final)

                        # Copia as demais colunas válidas
                        for col in df.columns:
                            if col in COLUNAS_VALIDAS_BANCO and col not in ["valor", "valor_realizado"]:
                                val = sanitize_val(row[col])

                                if col in ["realizado", "recorrente", "permite_parcial", "usar_media"]:
                                    if val is not None:
                                        val = bool(val)

                                item[col] = val

                        # MODO 3: Zerar Realizados se selecionado
                        if modo_importacao == "Suba todos os Lançamentos e seus Planejamentos, mas zere todos os Realizados":
                            item["realizado"] = False
                            item["valor_realizado"] = 0.0

                        # Força o vínculo com usuário e projeto
                        item["usuario_id"] = usr_id
                        item["projeto_id"] = proj_id

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

                    st.success(f"✅ Upload concluído com sucesso! {total} registro(s) processado(s).")
                except Exception as e:
                    st.error(f"Erro durante o upload: {e}")