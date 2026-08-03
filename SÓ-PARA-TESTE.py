import re
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

def format_date_str(val):
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

        dt_parsed = pd.to_datetime(val_str, dayfirst=True, errors="coerce")
        if not pd.isna(dt_parsed):
            return dt_parsed.strftime("%Y-%m-%d")
    except Exception:
        pass

    return None

def render_upload(usuario_id=None, projeto_id=None):
    st.subheader("📤 Importar Planejamento via Excel")

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
        st.error("⚠️ Usuário ou Projeto Ativo não identificados na sessão.")
        return

    st.info(f"📌 **Projeto Ativo:** `{proj_id}` | **Usuário:** `{usr_id}`")

    uploaded_file = st.file_uploader("Selecione a planilha com o Planejamento (.xlsx)", type=["xlsx"])

    if uploaded_file is not None:
        if st.button("Subir Planejamento", type="primary", use_container_width=True):
            with st.spinner("Processando e enviando dados..."):
                try:
                    df = pd.read_excel(uploaded_file, engine="openpyxl")

                    if df.empty:
                        st.warning("A planilha enviada está vazia.")
                        return

                    # Normaliza nomes de colunas da planilha (minúsculas e sem acentos)
                    df.columns = (
                        df.columns.astype(str)
                        .str.strip()
                        .str.lower()
                        .str.replace(" ", "_")
                        .str.replace("á", "a").str.replace("ã", "a")
                        .str.replace("é", "e").str.replace("ê", "e")
                        .str.replace("í", "i").str.replace("ó", "o")
                        .str.replace("ú", "u").str.replace("ç", "c")
                    )

                    # 1. DELETA TODOS OS LANÇAMENTOS ANTERIORES DO BANCO (PAIS E FILHOS)
                    st.toast("Limpando lançamentos anteriores do projeto...", icon="🗑️")
                    supabase.table("lancamentos") \
                        .delete() \
                        .eq("usuario_id", usr_id) \
                        .eq("projeto_id", proj_id) \
                        .execute()

                    records_para_envio = []

                    for _, row in df.iterrows():
                        # REGRA RÍGIDA: Se tiver parcial_real > 0 na planilha, deleta/ignora o lançamento
                        p_real = parse_float_val(row.get("parcial_real"))
                        if p_real > 0:
                            continue

                        descricao = str(sanitize_val(row.get("descricao")) or "").strip()
                        if not descricao:
                            continue  # ignora linhas em branco

                        tipo = str(sanitize_val(row.get("tipo")) or "").strip()
                        data_venc = format_date_str(sanitize_val(row.get("data_vencimento")) or sanitize_val(row.get("data")))

                        # Valor Planejado
                        val_plan = row.get("valor_plan")
                        if sanitize_val(val_plan) is None:
                            val_plan = row.get("valor")
                        final_plan = parse_float_val(val_plan)

                        permite_parcial = bool(sanitize_val(row.get("permite_parcial")) or False)
                        recorrente = bool(sanitize_val(row.get("recorrente")) or False)
                        categoria = sanitize_val(row.get("categoria"))
                        complemento = sanitize_val(row.get("complemento"))
                        observacao = sanitize_val(row.get("observacao"))

                        # APENAS O PLANEJAMENTO É MONTADO E GRAVADO
                        item = {
                            "usuario_id": usr_id,
                            "projeto_id": proj_id,
                            "descricao": descricao,
                            "tipo": tipo,
                            "data_vencimento": data_venc,
                            "data": data_venc,
                            "valor_plan": final_plan,
                            "valor": final_plan,
                            "permite_parcial": permite_parcial,
                            "recorrente": recorrente,
                            # DEFINIDOS RIGOROSAMENTE COMO PLANEJADO:
                            "valor_real": 0.0,
                            "parcial_real": 0.0,
                            "realizado": False,
                            "status": "PLAN"
                        }

                        if categoria:
                            item["categoria"] = categoria
                        if complemento:
                            item["complemento"] = complemento
                        if observacao:
                            item["observacao"] = observacao

                        records_para_envio.append(item)

                    total_proc = len(records_para_envio)
                    if total_proc == 0:
                        st.warning("Nenhum lançamento de planejamento válido encontrado na planilha.")
                        return

                    # Inserção em lotes no Supabase
                    progress_bar = st.progress(0)
                    processed_count = 0

                    for i in range(0, total_proc, BATCH_SIZE):
                        batch = records_para_envio[i:i + BATCH_SIZE]
                        supabase.table("lancamentos").insert(batch).execute()
                        processed_count += len(batch)
                        progress_bar.progress(processed_count / total_proc)

                    st.success(f"✅ Sucesso! {total_proc} lançamento(s) de planejamento importado(s) com status 'PLAN'. Registros de realização/parciais foram completamente descartados.")
                except Exception as e:
                    st.error(f"Erro durante o envio: {e}")