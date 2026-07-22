import streamlit as st

def renderizar_ajuda_gestao():
    """
    Renderiza o box de ajuda da tela de Gestão com a estilização correta.
    O texto e o HTML ficam centralizados apenas aqui.
    """
    st.markdown(
        """
        <div style="background-color: #007ba7; padding: 15px; border-radius: 5px; color: white; font-family: sans-serif; margin-bottom: 20px; position: relative;">
            <div style="font-size: 14px; text-align: justify; line-height: 1.4;">
                Se for sua primeira vez aqui no ORCAS, siga esse caminho:<br>
                <p>(1) Digite um nome para seu Plano no campo 02 e dê ENTER.</p><br>
                <p>(2) Se você quiser colocar um Saldo Inicial, utilize o campo 06.</p><br>
                <p>(3) Se você quiser receber um Resumo Diário via Whatsapp e/ou E-mail, utilize os campos 08 e 09.<br>
                (4) Escolha o tipo de Assinatura (Mensal, Semestral, Anual).<br>
                (5) Clique no campo 12. Salvar alterações ou Criar o novo Plano. <br>
                (6) 
                Esse Plano será criado contendo <b>24 meses</b> (padrão) iniciando a partir de hoje. Se você quiser 
                um Saldo Inicial, digite-o no campo 06. (3) Se vc quiser receber um Resumo Diário via e-mail e/ou Whatsapp, utilize os campos 08 e 09. (4) poderá aumentar o período de 24 para 36 ou 48 ou 60 meses, basta deslizar o comando 
                <b>“Aumentar Período”</b>, porém isso acarretará em um valor adicional. Você também pode incluir 
                o recebimento do Relatório Diário via email ou Whatsapp marcando as caixas de seleção abaixo.
            </div>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    # <div style="font-weight: bold; font-size: 16px; margin-bottom: 8px;">AJUDA – GESTÃO</div>

    if st.button("❌ Fechar Guia de Ajuda", key="btn_fechar_ajuda_gestao"):
        st.session_state["exibir_ajuda_gestao"] = False
        st.rerun()