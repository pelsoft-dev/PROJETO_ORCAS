import streamlit as st
import mercadopago

def exibir_pagamentos(supabase, ID_USUARIO_LOGADO):
    st.markdown('<div class="titulo-tela">💳 Finalizar Assinatura</div>', unsafe_allow_html=True)
    
    # 1. Recupera dados da sessão
    valor_base = st.session_state.get('valor_checkout', 29.75)
    descricao_plano = st.session_state.get('descricao_pag', "Assinatura ORCAS")
    
    st.info(f"**Plano Selecionado:** {descricao_plano}")
    st.write(f"**Valor do Período:** R$ {valor_base:.2f}")
    st.write("---")

    # --- 2. SISTEMA DE CUPOM (HÍBRIDO: % OU ABSOLUTO) ---
    cupom_input = st.text_input("Possui um Cupom de Desconto?", placeholder="Digite o código e aperte ENTER").upper()
    desconto_calculado = 0.0
    
    if cupom_input:
        try:
            # A busca agora funcionará pois você habilitou a tabela na API
            res = supabase.table("cupons").select("*").eq("codigo", cupom_input).eq("ativo", True).execute()
            if res.data:
                d = res.data[0]
                v_abs = float(d.get('valor_desconto', 0) or 0)
                v_perc = float(d.get('percentual_desconto', 0) or 0)

                # Regra: Prioriza percentual se ambos existirem
                if v_perc > 0:
                    desconto_calculado = valor_base * (v_perc / 100)
                    st.success(f"✅ Cupom de {v_perc}% aplicado!")
                else:
                    desconto_calculado = v_abs
                    st.success(f"✅ Cupom de R$ {v_abs:.2f} aplicado!")
            else:
                st.error("❌ Cupom inválido ou expirado.")
        except Exception as e:
            st.error(f"Erro ao validar cupom: {e}")

    # 3. Valor Final
    valor_final = max(valor_base - desconto_calculado, 1.00)
    
    # Estilização do Total
    st.markdown(f"### Total a Pagar: <span style='color:#009EE3'>R$ {valor_final:.2f}</span>", unsafe_allow_html=True)
    st.write("")

    # --- 4. BOTÃO ÚNICO AZUL (CONSOLIDADO) ---
    # Este botão gera o link e já fornece o acesso imediato
    if st.button(f"🚀 FINALIZAR PAGAMENTO DE R$ {valor_final:.2f}", use_container_width=True):
        with st.spinner("Gerando checkout seguro..."):
            url = criar_link_final(ID_USUARIO_LOGADO, valor_final, descricao_plano)
            if url:
                # O botão azul que você gostou, centralizado
                st.markdown(f'''
                    <div style="text-align: center; margin-top: 15px;">
                        <a href="{url}" target="_blank" style="text-decoration: none;">
                            <div style="background-color: #009EE3; color: white; padding: 22px; border-radius: 12px; font-weight: bold; font-size: 20px; box-shadow: 0px 4px 15px rgba(0,0,0,0.2);">
                                CLIQUE AQUI PARA ABRIR O MERCADO PAGO ➔
                            </div>
                        </a>
                        <p style="font-size: 13px; color: #666; margin-top: 10px;">O pagamento (Pix, Cartão ou Boleto) abrirá em nova aba.</p>
                    </div>
                ''', unsafe_allow_html=True)

    st.write("---")
    if st.button("⬅️ Voltar para Gestão"):
        st.session_state.escolha = "⚙️ Gestão"
        st.rerun()

def criar_link_final(user_id, valor, descricao):
    try:
        sdk = mercadopago.SDK(st.secrets["MP_ACCESS_TOKEN"])
        preference_data = {
            "items": [{"title": descricao, "quantity": 1, "unit_price": float(valor)}],
            "external_reference": str(user_id),
            "payment_methods": {
                "excluded_payment_methods": [{"id": "consumer_credits"}],
                "installments": 1 
            },
            "auto_return": "approved",
        }
        res = sdk.preference().create(preference_data)
        return res["response"]["init_point"]
    except Exception as e:
        st.error(f"Erro no Mercado Pago: {e}")
        return None