import io
import pandas as pd
import streamlit as st
from orcas_v01_security import supabase

def render_download(usuario_id=None, projeto_id=None):
    st.subheader("📥 Exportar Lançamentos")
    st.write("Baixe os lançamentos do seu projeto ativo em formato Excel (.xlsx).")

    # --- RESOLUÇÃO FLEXÍVEL DAS CHAVES DE SESSÃO ---
    # Tenta usar os parâmetros informados ou busca as variações comuns no session_state
    usr_id = usuario_id or st.session_state.get("user_id") or st.session_state.get("usuario_id") or st.session_state.get("usuario")
    proj_id = projeto_id or st.session_state.get("projeto_ativo") or st.session_state.get("projeto") or st.session_state.get("plano_ativo")

    if not usr_id or not proj_id:
        st.error("⚠️ Usuário ou Projeto Ativo não identificados na sessão. Efetue o login novamente.")
        return

    st.info(f"📌 **Filtro Aplicado:** Usuário `{usr_id}` | Projeto `{proj_id}`")

    if st.button("Gerar Planilha para Download", type="primary", use_container_width=True):
        with st.spinner("Buscando lançamentos no Supabase..."):
            try:
                # Consulta filtrada estritamente pelo usuario_id e projeto_id
                response = (
                    supabase.table("lancamentos")
                    .select("*")
                    .eq("usuario_id", usr_id)
                    .eq("projeto_id", proj_id)
                    .execute()
                )
                data = response.data

                if not data:
                    st.warning("Nenhum lançamento encontrado para este usuário e projeto.")
                    return

                df = pd.DataFrame(data)

                # Ordenação exata das colunas
                col_order = [
                    "id", "usuario_id", "descricao", "valor", "tipo", "data_vencimento",
                    "realizado", "valor_realizado", "categoria", "recorrente", "projeto_id",
                    "valor_plan", "valor_real", "status", "data", "permite_parcial",
                    "usar_media", "complemento_tipo", "complemento_texto", "correcao_freq",
                    "correcao_valor", "id_pai", "parcial_real", "parcial_data", "regra_parcial"
                ]
                existing_cols = [c for c in col_order if c in df.columns]
                df = df[existing_cols]

                # Exporta para memória RAM (BytesIO)
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Lancamentos")
                buffer.seek(0)

                st.success(f"✅ {len(df)} lançamentos processados com sucesso!")
                
                # Nome dinâmico para o arquivo exportado
                nome_arquivo = f"orcas_{proj_id}_lancamentos.xlsx".lower().replace(" ", "_")

                # Botão nativo para o usuário baixar no navegador
                st.download_button(
                    label="💾 Clique aqui para Baixar o Arquivo Excel",
                    data=buffer,
                    file_name=nome_arquivo,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Erro ao exportar lançamentos: {e}")