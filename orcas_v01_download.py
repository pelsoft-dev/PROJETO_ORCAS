import io
import pandas as pd
import streamlit as st
from orcas_v01_security import supabase

def render_download():
    st.subheader("📥 Exportar Lançamentos")
    st.write("Baixe os lançamentos do seu projeto ativo em formato Excel (.xlsx).")

    # --- VALIDAÇÕES DE SEGURANÇA E CONTEXTO ---
    usuario_id = st.session_state.get("user_id")
    projeto_id = st.session_state.get("projeto_ativo")

    if not usuario_id or not projeto_id:
        st.error("⚠️ Usuário ou Projeto Ativo não identificados na sessão. Efetue o login novamente.")
        return

    st.info(f"📌 **Filtro Aplicado:** Usuário ID `{usuario_id}` | Projeto `{projeto_id}`")

    if st.button("Gerar Planilha para Download", type="primary", use_container_width=True):
        with st.spinner("Buscando lançamentos no Supabase..."):
            try:
                # Consulta filtrada estritamente pelo usuario_id e projeto_id
                response = (
                    supabase.table("lancamentos")
                    .select("*")
                    .eq("usuario_id", usuario_id)
                    .eq("projeto_id", projeto_id)
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
                nome_arquivo = f"orcas_{projeto_id}_lancamentos.xlsx".lower().replace(" ", "_")

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