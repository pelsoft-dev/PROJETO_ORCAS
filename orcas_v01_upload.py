import re
import math
import datetime
import pandas as pd
import streamlit as st
from orcas_v01_security import supabase

BATCH_SIZE = 100

COLUNAS_VALIDAS_BANCO = {
    "id",
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
    "status"
}

def sanitize_val(val):
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    return val

def format_date_str(val):
    """
    Normaliza QUALQUER formato de data inserido pelo usuário final 
    para o formato ISO 'YYYY-MM-DD' exigido pelo Supabase.
    """
    if pd.isna(val) or val is None:
        return None
    
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ["none", "nan", "nat", "null"]:
        return None

    val_str = val_str.split(" ")[0].strip()

    try:
        # 1. Objeto Date / Datetime / Timestamp
        if hasattr(val, "strftime") and callable(getattr(val, "strftime")):
            return val.strftime("%Y-%m-%d")

        # 2. Número Serial do Excel (ex: 46263 ou 46263.0)
        if isinstance(val, (int, float)) or val_str.replace(".", "", 1).isdigit():
            num_val = float(val)
            if num_val > 30000:
                return pd.to_datetime(num_val, unit="D", origin="1899-12-30").strftime("%Y-%m-%d")

        # 3. String em formato ISO YYYY-MM-DD
        match_iso = re.match(r"^(\d{4})[-/. ](\d{1,2})[-/. ](\d{1,2})$", val_str)
        if match_iso:
            ano, mes, dia = match_iso.groups()
            return f"{int(ano):04d}-{int(mes):02d}-{int(dia):02d}"

        # 4. String em formato BR DD/MM/YYYY
        match_br = re.match(r"^(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{2,4})$", val_str)
        if match_br:
            dia, mes, ano = match_br.groups()
            if len(ano) == 2:
                ano = "20" + ano
            return f"{int(ano):04d}-{int(mes):02d}-{int(dia):02d}"

        # 5. Parsing genérico via Pandas
        dt_parsed = pd.to_datetime(val_str, dayfirst=True, errors="coerce")
        if not pd.isna(dt_parsed):
            return dt_parsed.strftime("%Y-%m-%d")

    except Exception:
        pass

    return None

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

                    # MODO 1: Apagar dados existentes antes do envio
                    if modo_importacao == "Apague todos os dados do DB e suba todo o conteúdo da planilha":
                        st.toast("Limpando lançamentos anteriores do projeto...", icon="🗑️")
                        supabase.table("lancamentos") \
                            .delete() \
                            .eq("usuario_id", usr_id) \
                            .eq("projeto_id", proj_id) \
                            .execute()

                    # Formatação universal de colunas de data na planilha
                    for col in ["data_vencimento", "data", "parcial_data"]:
                        if col in df.columns:
                            df[col] = df[col].apply(format_date_str)

                    # Dicionários de índice rápido para o MODO 2
                    lookup_normais = {}    # Chave: (descricao, data, tipo) -> id
                    lookup_parciais = {}   # Chave: (descricao, parcial_data) -> id

                    if modo_importacao == "Lançamentos novos serão cadastrados, e os já existentes serão atualizados":
                        res = supabase.table("lancamentos") \
                            .select("*") \
                            .eq("usuario_id", usr_id) \
                            .eq("projeto_id", proj_id) \
                            .execute()
                        
                        raw_data = res.data or []
                        for db_row in raw_data:
                            desc = str(db_row.get("descricao") or "").strip()
                            tp = str(db_row.get("tipo") or "").strip()
                            dt = format_date_str(db_row.get("data_vencimento") or db_row.get("data"))
                            p_dt = format_date_str(db_row.get("parcial_data"))
                            db_id = db_row.get("id")

                            if db_id is not None:
                                if desc and dt and tp:
                                    lookup_normais[(desc, dt, tp)] = db_id
                                if desc and p_dt:
                                    lookup_parciais[(desc, p_dt)] = db_id

                    records_para_envio = []

                    for _, row in df.iterrows():
                        # --- 1. DECLARAÇÃO / LEITURA DE TODAS AS VARIÁVEIS BASE (PRIMEIRA COISA DA ITERAÇÃO) ---
                        descricao = str(sanitize_val(row.get("descricao")) or "").strip()
                        tipo = str(sanitize_val(row.get("tipo")) or "").strip()
                        data_venc = format_date_str(sanitize_val(row.get("data_vencimento")) or sanitize_val(row.get("data")))
                        parcial_data = format_date_str(sanitize_val(row.get("parcial_data")))
                        
                        parcial_real = float(sanitize_val(row.get("parcial_real")) or 0.0)
                        permite_parcial = bool(sanitize_val(row.get("permite_parcial")) or False)

                        # --- 2. REGRA DO MODO 3 (Pula parciais se necessário) ---
                        if modo_importacao == "Suba todos os Lançamentos e seus Planejamentos, mas zere todos os Realizados":
                            if parcial_real > 0:
                                continue

                        # Resgate de valores planejados e realizados
                        val_orig = sanitize_val(row.get("valor"))
                        val_plan = sanitize_val(row.get("valor_plan"))
                        val_real = sanitize_val(row.get("valor_real"))
                        val_realizado = sanitize_val(row.get("valor_realizado"))

                        final_plan = float(val_plan if val_plan is not None else (val_orig or 0.0))
                        final_real = float(val_real if val_real is not None else (val_realizado or parcial_real or 0.0))

                        # Objeto base para montagem
                        item = {
                            "usuario_id": usr_id,
                            "projeto_id": proj_id,
                            "descricao": descricao,
                            "tipo": tipo,
                            "valor_plan": final_plan,
                            "valor_real": final_real,
                            "data_vencimento": data_venc,
                            "data": data_venc
                        }

                        if parcial_data:
                            item["parcial_data"] = parcial_data

                        # Copia colunas válidas restantes garantindo sanitização
                        for col in df.columns:
                            if col in COLUNAS_VALIDAS_BANCO and col not in ["valor_plan", "valor_real", "id", "data_vencimento", "data", "parcial_data"]:
                                val = sanitize_val(row[col])
                                if col in ["realizado", "recorrente", "permite_parcial", "usar_media"]:
                                    if val is not None:
                                        val = bool(val)
                                item[col] = val

                        # Ajustes do Modo 3 (Zerar realizados)
                        if modo_importacao == "Suba todos os Lançamentos e seus Planejamentos, mas zere todos os Realizados":
                            item["valor_real"] = 0.0
                            item["realizado"] = False
                            item["parcial_real"] = 0.0

                        # --- 3. MODO 2: LÓGICA DE ATUALIZAÇÃO SEM DUPLICAÇÃO ---
                        if modo_importacao == "Lançamentos novos serão cadastrados, e os já existentes serão atualizados":
                            
                            # CENÁRIO 3: Lançamento Filho Parcial (permite_parcial == False e parcial_real > 0)
                            if not permite_parcial and parcial_real > 0:
                                match_id = lookup_parciais.get((descricao, parcial_data))
                                if match_id:
                                    item["id"] = match_id
                                    item["parcial_real"] = parcial_real

                            # CENÁRIO 2: Lançamento Pai (permite_parcial == True)
                            elif permite_parcial:
                                match_id = lookup_normais.get((descricao, data_venc, tipo))
                                if match_id:
                                    item["id"] = match_id
                                    item["valor_plan"] = final_plan
                                    item.pop("valor_real", None)

                            # CENÁRIO 1: Lançamento Normal (permite_parcial == False e parcial_real == 0)
                            else:
                                match_id = lookup_normais.get((descricao, data_venc, tipo))
                                if match_id:
                                    item["id"] = match_id
                                    item["valor_plan"] = final_plan
                                    item["valor_real"] = final_real

                        records_para_envio.append(item)

                    # Envio em lotes (Batches)
                    progress_bar = st.progress(0)
                    total = len(records_para_envio)
                    uploaded_count = 0

                    if total == 0:
                        st.warning("Nenhum lançamento válido para importar após a filtragem.")
                        return

                    for i in range(0, total, BATCH_SIZE):
                        batch = records_para_envio[i:i + BATCH_SIZE]
                        supabase.table("lancamentos").upsert(batch).execute()
                        uploaded_count += len(batch)
                        progress_bar.progress(uploaded_count / total)

                    st.success(f"✅ Upload concluído com sucesso! {total} registro(s) processado(s).")
                except Exception as e:
                    st.error(f"Erro durante o upload: {e}")