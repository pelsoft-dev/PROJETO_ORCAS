import streamlit as st
import mercadopago
from datetime import datetime

def exibir_pagamentos(supabase, ID_USUARIO_LOGADO):
    st.markdown('<div class="titulo-tela">💳 Finalizar Assinatura</div>', unsafe_allow_html=True)
    
    # 1. Recupera os dados enviados pela Gestão
    valor_base = st.session_state.get('valor_checkout', 19.90)
    descricao_plano = st.session_state.get('descricao_pag', "Assinatura ORCAS")
    
    st.write("### Resumo do Pedido")
    st.info(f"**Plano Selecionado:** {descricao_plano}")
    
    col_v1, col_v2 = st.columns(2)
    col_v1.metric("Valor do Período", f"R$ {valor_base:.2f}")

    # --- 2. SISTEMA DE CUPOM ---
    st.write("---")
    cupom_input = st.text_input("Possui um Cupom de Desconto?", placeholder="Ex: ABCDEFGHIJ", key="cp_final_input").upper()
    desconto_cupom = 0.0
    
    if cupom_input:
        try:
            res = supabase.table("cupons").select("*").eq("codigo", cupom_input).eq("ativo", True).execute()
            if res.data:
                desconto_cupom = float(res.data[0]['valor_desconto'])
                st.success(f"✅ Cupom '{cupom_input}' aplicado! Desconto de R$ {desconto_cupom:.2f}")
            else:
                st.error("❌ Cupom inválido ou expirado.")
        except Exception as e:
            st.error(f"Erro ao validar cupom: {e}")

    # 3. Cálculo do Valor Final
    valor_final = max(valor_base - desconto_cupom, 1.00)
    
    if desconto_cupom > 0:
        col_v2.metric("Total com Desconto", f"R$ {valor_final:.2f}", delta=f"- R$ {desconto_cupom:.2f}")
    else:
        col_v2.empty()

    st.write("")
    st.write("Clique abaixo para gerar o link oficial de pagamento do Mercado Pago.")

    # --- 4. CHAMADA DA FUNÇÃO DE CHECKOUT ---
    if st.button("GERAR LINK DE PAGAMENTO", use_container_width=True, type="primary"):
        gerar_checkout_pro(ID_USUARIO_LOGADO, valor_final, descricao_plano)

    # --- 5. BOTÃO DE RETORNO ---
    st.write("---")
    if st.button("⬅️ Cancelar e Voltar para Gestão"):
        st.session_state.escolha = "⚙️ Gestão"
        st.rerun()

def gerar_checkout_pro(user_id, valor, descricao):
    """
    Função dedicada para interface com a API do Mercado Pago.
    """
    try:
        sdk = mercadopago.SDK(st.secrets["MP_ACCESS_TOKEN"])
        
        preference_data = {
            "items": [
                {
                    "title": descricao,
                    "quantity": 1,
                    "unit_price": float(valor),
                }
            ],
            "external_reference": str(user_id),
            "back_urls": {
                "success": "https://seu-app.streamlit.app/", 
                "failure": "https://seu-app.streamlit.app/",
                "pending": "https://seu-app.streamlit.app/"
            },
            "auto_return": "approved",
        }
        
        preference_response = sdk.preference().create(preference_data)
        url_pagamento = preference_response["response"]["init_point"]
        
        # Exibe o botão de redirecionamento estilizado
        st.markdown(f'''
            <div style="text-align: center; margin-top: 20px;">
                <a href="{url_pagamento}" target="_blank" style="text-decoration: none;">
                    <div style="background-color: #009EE3; color: white; padding: 18px; border-radius: 8px; font-weight: bold; font-size: 20px; box-shadow: 0px 4px 10px rgba(0,0,0,0.1);">
                        PAGAR AGORA COM MERCADO PAGO
                    </div>
                </a>
                <p style="font-size: 12px; color: #666; margin-top: 10px;">O ambiente de pagamento abrirá em uma nova aba.</p>
            </div>
        ''', unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"Erro ao conectar com Mercado Pago: {e}")