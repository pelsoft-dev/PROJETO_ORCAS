import streamlit as st
import mercadopago

def exibir_pagamentos(supabase, ID_USUARIO_LOGADO):
    st.markdown('<div class="titulo-tela">💳 Finalizar Assinatura</div>', unsafe_allow_html=True)
    
    # 1. Recupera os dados enviados pela Gestão
    valor_base = st.session_state.get('valor_checkout', 0.0)
    descricao_plano = st.session_state.get('descricao_pag', "Assinatura ORCAS")
    
    if valor_base == 0:
        st.warning("⚠️ Nenhum valor de checkout encontrado. Por favor, volte à tela de Gestão.")
        if st.button("⬅️ Voltar para Gestão"):
            st.session_state.escolha = "⚙️ Gestão"
            st.rerun()
        return

    st.write("### Resumo do Pedido")
    st.info(f"**Plano Selecionado:** {descricao_plano}")
    
    # --- 2. SISTEMA DE CUPOM ---
    st.write("---")
    cupom_input = st.text_input("Possui um Cupom de Desconto?", placeholder="Ex: ABCDEFG", key="cp_final_input").upper()
    desconto_cupom = 0.0
    
    if cupom_input:
        try:
            # Com as novas Policies, o SELECT funcionará aqui:
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
    
    col_v1, col_v2 = st.columns(2)
    col_v1.metric("Valor Base", f"R$ {valor_base:.2f}")
    if desconto_cupom > 0:
        col_v2.metric("Total com Desconto", f"R$ {valor_final:.2f}", delta=f"- R$ {desconto_cupom:.2f}")

    st.write("")
    st.write("Ao clicar no botão abaixo, geraremos o seu link seguro de pagamento.")

    # --- 4. BOTÃO CONSOLIDADO (GERAR E EXIBIR) ---
    if st.button("🚀 GERAR E PAGAR AGORA", use_container_width=True, type="primary"):
        url_pagamento = criar_preferencia_mp(ID_USUARIO_LOGADO, valor_final, descricao_plano)
        
        if url_pagamento:
            st.markdown(f'''
                <div style="text-align: center; margin-top: 20px;">
                    <a href="{url_pagamento}" target="_blank" style="text-decoration: none;">
                        <div style="background-color: #009EE3; color: white; padding: 18px; border-radius: 8px; font-weight: bold; font-size: 20px; box-shadow: 0px 4px 10px rgba(0,0,0,0.1);">
                            CLIQUE AQUI PARA ABRIR O CHECKOUT
                        </div>
                    </a>
                    <p style="font-size: 13px; color: #666; margin-top: 12px;">Escolha <b>PIX, Cartão ou Boleto</b> na tela que abrirá.</p>
                </div>
            ''', unsafe_allow_html=True)

    # Botão de escape
    st.write("---")
    if st.button("⬅️ Cancelar e Voltar"):
        st.session_state.escolha = "⚙️ Gestão"
        st.rerun()

def criar_preferencia_mp(user_id, valor, descricao):
    """Função interna para configurar o Mercado Pago e evitar financiamentos indesejados"""
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
            "payment_methods": {
                "excluded_payment_methods": [
                    {"id": "consumer_credits"} # Tenta remover a linha de crédito/financiamento
                ],
                "installments": 1 # Prioriza a exibição do valor à vista
            },
            "back_urls": {
                "success": "https://seu-app.streamlit.app/", 
                "failure": "https://seu-app.streamlit.app/",
                "pending": "https://seu-app.streamlit.app/"
            },
            "auto_return": "approved",
        }
        
        preference_response = sdk.preference().create(preference_data)
        return preference_response["response"]["init_point"]
        
    except Exception as e:
        st.error(f"Erro ao conectar com Mercado Pago: {e}")
        return None