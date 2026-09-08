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
                <b>Se for sua 1ª vez ou quiser criar um outro Plano no ORCAS, siga esse caminho:</b><br>
                .   (1) Digite um nome para seu Plano no campo 02 e dê ENTER.<br>
                .   (2) Se você quiser receber um Resumo Diário via Whatsapp e/ou E-mail, utilize os campos 08/09. Terá um acréscimo de 9,85.<br>
                .   (3) Escolha o tipo de Assinatura no campo 11 (Mensal, Semestral, Anual).<br>
                .   (4) Clique no botão "12. Salvar alterações ou Criar o novo Plano". <br>
                .   (5) Se tiver Cupom de Desconto, digite-o no campo 21 e dê ENTER.<br>
                .   (6) Com ou sem Cupom, agora clique no botão "22. GERAR LINK DE PAGAMENTO".<br>
                .   (7) Clique no botão "30. PAGAMENTO - IR P/ MERCADO PAGO".<br>
                <b>Se quiser apenas carregar um Plano já existente, clique sobre o campo 01 e escolha.</b><br>
                .   A qualquer momento você pode mudar a configuração de seu plano (saldo inicial, aumentar o número de meses, resumo diário, etc)
            </div>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    # <div style="font-weight: bold; font-size: 16px; margin-bottom: 8px;">AJUDA – GESTÃO</div>

    # if st.button("❌ Fechar Guia de Ajuda", key="btn_fechar_ajuda_gestao"):
        # st.session_state["exibir_ajuda_gestao"] = False
        # st.rerun()