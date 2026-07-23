import streamlit as st

def renderizar_ajuda_gestao():
    """
    Renderiza os blocos expansíveis de ajuda da tela de Gestão.
    """
    with st.expander("▶ Se for sua 1ª vez ou quiser criar um outro Plano no ORCAS"):
        st.markdown(
            """
            <div style="background-color: #007ba7; padding: 15px; border-radius: 5px; color: white; font-family: sans-serif; margin-bottom: 20px; position: relative;">
                <div style="font-size: 14px; text-align: justify; line-height: 1.4;">
                    * **(1)** Digite um nome para seu Plano no campo 02 e dê ENTER.
                    * **(2)** Se você quiser receber um Resumo Diário via Whatsapp e/ou E-mail, utilize os campos 08 e 09.
                    * **(3)** Escolha o tipo de Assinatura (Mensal, Semestral, Anual).
                    * **(4)** Clique no campo 12. Salvar alterações ou Criar o novo Plano.
                    * **(5)** Se tiver Cupom de Desconto, digite-o no campo 21 e dê ENTER.
                    * **(6)** Com ou sem Cupom, agora clique no botão **"22. GERAR LINK DE PAGAMENTO"**.
                    * **(7)** Clique no botão **"30. PAGAMENTO - IR P/ MERCADO PAGO"**.
                </div>
            </div>
            """
        )

    with st.expander("▶ Se quiser apenas carregar um Plano já existente"):
        st.markdown(
            """
            * Clique sobre o **campo 01** e escolha o plano desejado.
            * A qualquer momento você pode mudar a configuração de seu plano (saldo inicial, aumentar o número de meses, resumo diário, etc.).
            """
        )