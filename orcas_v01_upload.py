import re
import math
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
    """Sanitiza valores vindos do Pandas/Excel."""
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    return val

def parse_float_val(val):
    """Converte valores numéricos para float, tratando formatações PT-BR."""
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

def format_date_str(val):
    """Normaliza datas do Excel para YYYY-MM-DD."""
    if pd.isna(val) or val is None:
        return None
    
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ["none", "nan", "nat", "null"]:
        return None

    val_str = val_str.split(" ")[0].strip()

    try:
        if hasattr(val, "strftime") and callable(getattr(val, "strftime")):
            return val.strftime("%Y-%m-%d")

        if isinstance(val, (int, float)) or val_str.replace(".", "", 1).isdigit():
            num_val = float(val)
            if num_val > 30000:
                return pd.to_datetime(num_val, unit="D", origin="1899-12-30").strftime("%Y-%m-%d")

        match_br = re.match(r"^(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{2,4})$", val_str)
        if match_br:
            dia, mes, ano = match_br.groups()
            if len(ano) == 2:
                ano = "20" + ano
            return f"{int(ano):04d}-{int(mes):02d}-{int(dia):02d}"

        match_iso = re.match(r"^(\d{4})[-/. ](\d{1,2})[-/. ](\d{1,2})$", val_str)
        if match_iso:
            ano, mes, dia = match_iso.groups()
            return f"{int(ano):04d}-{int(mes):02d}-{int(dia):02d}"

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

                    # Dicionários de busca rápida para o MODO 2
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
                            d_desc = str(db_row.get("descricao") or "").strip()
                            d_tp = str(db_row.get("tipo") or "").strip()
                            d_dt = format_date_str(db_row.get("data_vencimento") or db_row.get("data"))
                            d_p_dt = format_date_str(db_row.get("parcial_data"))
                            db_id = db_row.get("id")

                            if db_id is not None:
                                if d_desc and d_dt and d_tp:
                                    lookup_normais[(d_desc, d_dt, d_tp)] = db_id
                                if d_desc and d_p_dt:
                                    lookup_parciais[(d_desc, d_p_dt)] = db_id

                    records_novos = []       # Registros SEM ID -> Usam .insert()
                    records_existentes = []  # Registros COM ID -> Usam .upsert()

                    for _, row in df.iterrows():
                        descricao = str(sanitize_val(row.get("descricao")) or "").strip()
                        tipo = str(sanitize_val(row.get("tipo")) or "").strip()
                        data_venc = format_date_str(sanitize_val(row.get("data_vencimento")) or sanitize_val(row.get("data")))
                        parcial_data = format_date_str(sanitize_val(row.get("parcial_data")))
                        
                        parcial_real = parse_float_val(row.get("parcial_real"))
                        permite_parcial = bool(sanitize_val(row.get("permite_parcial")) or False)

                        # MODO 3: Ignora linhas de parciais realizadas
                        if modo_importacao == "Suba todos os Lançamentos e seus Planejamentos, mas zere todos os Realizados":
                            if parcial_real > 0:
                                continue

                        val_orig = parse_float_val(row.get("valor"))
                        val_plan = row.get("valor_plan")
                        val_real = row.get("valor_real")
                        val_realizado = row.get("valor_realizado")

                        final_plan = parse_float_val(val_plan) if sanitize_val(val_plan) is not None else val_orig
                        raw_real = val_real if sanitize_val(val_real) is not None else val_realizado
                        final_real = parse_float_val(raw_real) if sanitize_val(raw_real) is not None else parcial_real

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

                        for col in df.columns:
                            if col in COLUNAS_VALIDAS_BANCO and col not in ["valor_plan", "valor_real", "id", "data_vencimento", "data", "parcial_data"]:
                                val = sanitize_val(row[col])
                                if col in ["realizado", "recorrente", "permite_parcial", "usar_media"]:
                                    if val is not None:
                                        val = bool(val)
                                elif col in ["valor", "valor_realizado", "parcial_real", "correcao_valor"]:
                                    val = parse_float_val(val)
                                item[col] = val

                        if modo_importacao == "Suba todos os Lançamentos e seus Planejamentos, mas zere todos os Realizados":
                            item["valor_real"] = 0.0
                            item["realizado"] = False
                            item["parcial_real"] = 0.0

                        # MODO 2: ATRIBUIÇÃO DE ID
                        assigned_id = None
                        if modo_importacao == "Lançamentos novos serão cadastrados, e os já existentes serão atualizados":
                            if not permite_parcial and parcial_real > 0:
                                assigned_id = lookup_parciais.pop((descricao, parcial_data), None)
                                if assigned_id is not None:
                                    item["parcial_real"] = parcial_real

                            elif permite_parcial:
                                assigned_id = lookup_normais.pop((descricao, data_venc, tipo), None)
                                if assigned_id is not None:
                                    item["valor_plan"] = final_plan
                                    item.pop("valor_real", None)

                            else:
                                assigned_id = lookup_normais.pop((descricao, data_venc, tipo), None)
                                if assigned_id is not None:
                                    item["valor_plan"] = final_plan
                                    item["valor_real"] = final_real

                        # SEPARAÇÃO CRÍTICA ENTRE NOVOS E EXISTENTES
                        if assigned_id is not None and not pd.isna(assigned_id):
                            item["id"] = assigned_id
                            records_existentes.append(item)
                        else:
                            # Garante que NENHUMA chave "id" exista no dicionário de novos
                            item.pop("id", None)
                            records_novos.append(item)

                    total_proc = len(records_novos) + len(records_existentes)
                    if total_proc == 0:
                        st.warning("Nenhum lançamento válido para importar após a filtragem.")
                        return

                    progress_bar = st.progress(0)
                    processed_count = 0

                    # 1. ENVIO DOS REGISTROS NOVOS (INSERT SEM ID)
                    if records_novos:
                        for i in range(0, len(records_novos), BATCH_SIZE):
                            batch = records_novos[i:i + BATCH_SIZE]
                            supabase.table("lancamentos").insert(batch).execute()
                            processed_count += len(batch)
                            progress_bar.progress(processed_count / total_proc)

                    # 2. ENVIO DOS REGISTROS EXISTENTES (UPSERT COM ID)
                    if records_existentes:
                        for i in range(0, len(records_existentes), BATCH_SIZE):
                            batch = records_existentes[i:i + BATCH_SIZE]
                            supabase.table("lancamentos").upsert(batch).execute()
                            processed_count += len(batch)
                            progress_bar.progress(processed_count / total_proc)

                    st.success(f"✅ Upload concluído com sucesso! {total_proc} registro(s) processado(s) ({len(records_novos)} novos inseridos e {len(records_existentes)} atualizados).")
                except Exception as e:
                    st.error(f"Erro durante o upload: {e}")