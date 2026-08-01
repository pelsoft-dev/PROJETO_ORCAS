import io
import pandas as pd
import streamlit as st
from orcas_v01_security import supabase

def render_download():
    st.subheader("📥 Exportar Lançamentos")
    st.write("Baixe a tabela completa de lançamentos em formato Excel (.xlsx).")

    if st.button("Gerar Planilha para Download"):
        with st.spinner("Buscando dados no Supabase..."):
            try:
                response = supabase.table("lancamentos").select("*").execute()
                data = response.data

                if not data:
                    st.warning("Nenhum registro encontrado na tabela 'lancamentos'.")
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

                # Exporta para memória RAM (BytesIO) sem salvar em disco
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Lancamentos")
                buffer.seek(0)

                st.success("Planilha gerada com sucesso!")
                
                # Botão nativo do Streamlit para o usuário baixar no navegador
                st.download_button(
                    label="💾 Baixar Arquivo Excel",
                    data=buffer,
                    file_name="orcas_lancamentos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as e:
                st.error(f"Erro ao exportar lançamentos: {e}")