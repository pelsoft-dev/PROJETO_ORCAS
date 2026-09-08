import streamlit as st


def renderizar_ajuda_gestao():
    """Renderiza o vídeo de ajuda via link do YouTube."""
    url_video = "https://www.youtube.com/watch?v=SEU_VIDEO_AQUI"

    st.markdown(
        """
        <div style="background-color: #007ba7; padding: 10px; border-radius: 8px; margin-bottom: 20px;">
        """,
        unsafe_allow_html=True,
    )

    st.video(url_video)

    st.markdown("</div>", unsafe_allow_html=True)