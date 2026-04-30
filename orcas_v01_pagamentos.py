import streamlit as st
import mercadopago

def exibir_pagamentos(supabase, ID_USUARIO_LOGADO):
    st.markdown('<div class="titulo-tela">💳 Finalizar Assinatura</div>', unsafe_allow_html=True)
    
    # 1. Recupera os dados da sessão
    valor_base = st.session_state.get('valor_checkout', 0.0)
    descricao_plano = st.session_state.get('descricao_pag', "Assinatura ORCAS")
    
    if valor_base == 0:
        st.warning("⚠️ Valor não identificado. Retorne à tela de Gestão.")
        if st.button("⬅️ Voltar para Gestão"):
            st.session_state.escolha = "⚙️ Gestão"
            st.rerun()
        return

    st.write("### Resumo do Pedido")
    st.info(f"**Plano Selecionado:** {descricao_plano}")
    
    # --- 2. SISTEMA DE CUPOM (HÍBRIDO: VALOR OU PERCENTUAL) ---
    st.write("---")
    cupom_input = st.text_input("Possui um Cupom de Desconto?", placeholder="Ex: PROMO50", key="cp_final_input").upper()
    desconto_calculado = 0.0
    
    if cupom_input:
        try:
            res = supabase.table("cupons").select("*").eq("codigo", cupom_input).eq("ativo", True).execute()
            if res.data:
                dados_cupom = res.data[0]
                v_abs = float(dados_cupom.get('valor_desconto', 0) or 0)
                v_perc = float(dados_cupom.get('percentual_desconto', 0) or 0)

                # Regra: Se tiver percentual, ele ganha. Se não, usa valor fixo.
                if v_perc > 0:
                    desconto_calculado = valor_base * (v_perc / 100)
                    label_desc = f"{v_perc}% OFF"
                else:
                    desconto_calculado = v_abs
                    label_desc = f"R$ {v_abs:.2f} OFF"

                st.success(f"✅ Cupom aplicado: {label_desc}")
            else:
                st.error("❌ Cupom inválido ou expirado.")
        except Exception as e:
            st.error(f"Erro ao validar cupom: {e}")

    # 3. Cálculo Final
    valor_final = max(valor_base - desconto_calculado, 1.00)
    
    col_v1, col_v2 = st.columns(2)
    col_v1.metric("Valor Base", f"R$ {valor_base:.2f}")
    if desconto_calculado > 0:
        col_v2.metric("Total com Desconto", f"R$ {valor_final:.2f}", delta=f"- R$ {desconto_calculado:.2f}")

    st.write("")
    
    # --- 4. BOTÃO CONSOLIDADO (Apenas 1 clique para gerar e mostrar o link) ---
    if st.button("🚀 GERAR E PAGAR AGORA", use_container_width=True, type="primary"):
        with st.spinner("Conectando ao Mercado Pago..."):
            url_pagamento = criar_preferencia_mp(ID_USUARIO_LOGADO, valor_final, descricao_plano)
            
            if url_pagamento:
                st.markdown(f'''
                    <div style="text-align: center; margin-top: 20px;">
                        <a href="{url_pagamento}" target="_blank" style="text-decoration: none;">
                            <div style="background-color: #009EE3; color: white; padding: 20px; border-radius: 10px; font-weight: bold; font-size: 22px; box-shadow: 0px 4px 15px rgba(0,0,0,0.2);">
                                CLIQUE AQUI PARA ABRIR O MERCADO PAGO ➔
                            </div>
                        </a>
                        <p style="font-size: 13px; color: #666; margin-top: 12px;">Escolha <b>PIX, Cartão ou Boleto</b> na aba que será aberta.</p>
                    </div>
                ''', unsafe_allow_html=True)

    st.write("---")
    if st.button("⬅️ Cancelar e Voltar"):
        st.session_state.escolha = "⚙️ Gestão"
        st.rerun()

def criar_preferencia_mp(user_id, valor, descricao):
    try:
        sdk = mercadopago.SDK(st.secrets["MP_ACCESS_TOKEN"])
        preference_data = {
            "items": [{"title": descricao, "quantity": 1, "unit_price": float(valor)}],
            "external_reference": str(user_id),
            "payment_methods": {
                "excluded_payment_methods": [{"id": "consumer_credits"}],
                "installments": 1 
            },
            "back_urls": {
                "success": "https://seu-app.streamlit.app/", 
                "failure": "https://seu-app.streamlit.app/",
                "pending": "https://seu-app.streamlit.app/"
            },
            "auto_return": "approved",
        }
        res = sdk.preference().create(preference_data)
        return res["response"]["init_point"]
    except Exception as e:
        st.error(f"Erro ao conectar com Mercado Pago: {e}")
        return None