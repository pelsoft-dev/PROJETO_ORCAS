# --- BLOCO DE SELEÇÃO DE PAGAMENTO (Agora fora da condição principal para aparecer sempre) ---
    st.write("---")
    st.subheader("💳 Finalizar Assinatura")
    
    tipo_pagamento = st.radio(
        "Escolha o período de renovação:",
        ["Mensal (Sem desconto)", "6 Meses (5% de desconto)", "12 Meses (11% de desconto)"],
        horizontal=True, key="radio_pag_final_v5"
    )

    if "6 Meses" in tipo_pagamento:
        qtd_meses = 6
        v_base = (v_mensal_total * 6) * (1 - DESC_6_MESES)
        label_desc = "5% OFF"
    elif "12 Meses" in tipo_pagamento:
        qtd_meses = 12
        v_base = (v_mensal_total * 12) * (1 - DESC_12_MESES)
        label_desc = "11% OFF"
    else:
        qtd_meses = 1
        v_base = v_mensal_total
        label_desc = "Valor Padrão"

    st.write("")
    cupom_in = st.text_input("Possui um Cupom de Desconto?", key="cp_gest_final_v3").upper()
    desc_extra = 0.0
    if cupom_in:
        try:
            res_c = supabase.table("cupons").select("*").eq("codigo", cupom_in).eq("ativo", True).execute()
            if res_c.data:
                d = res_c.data[0]
                v_p = float(d.get('percentual_desconto', 0) or 0)
                v_a = float(d.get('valor_desconto', 0) or 0)
                desc_extra = v_base * (v_p / 100) if v_p > 0 else v_a
                st.success("✅ Cupom aplicado!")
            else:
                st.error("❌ Cupom inválido.")
        except: pass

    valor_final = max(v_base - desc_extra, 1.00)

    # CSS PARA CORES
    st.markdown("""
        <style>
        div.stButton > button:has(div:contains("🚀")) { background-color: #28a745 !important; color: white !important; border: none !important; }
        div.stButton > button:has(div:contains("CLIQUE")) { background-color: #009EE3 !important; color: white !important; border: none !important; font-weight: bold !important; }
        div.stButton > button:has(div:contains("🔍")) { background-color: #f0f2f6 !important; color: #31333F !important; border: 1px solid #dcdfe6 !important; }
        </style>
    """, unsafe_allow_html=True)

    col_res1, col_res2 = st.columns([2, 1])
    with col_res1:
        st.write(f"**Total a pagar:** :green[R$ {valor_final:.2f}] ({label_desc})")
    
    with col_res2:
        if st.button("🚀 PAGAR AGORA", use_container_width=True):
            import orcas_v01_pagamentos as pag
            email_user = st.session_state.get('usuario_email', "cliente@email.com")
            
            link, pref_id = pag.criar_link_final(
                ID_USUARIO_LOGADO, 
                valor_final, 
                f"Assinatura ORCAS - {qtd_meses} Meses",
                email_user,
                qtd_meses
            )
            if link:
                st.session_state.url_ativa = link
                st.session_state.pref_id_ativa = pref_id # Salva o ID da preferência para consulta
                st.session_state.meses_comprados = qtd_meses
                st.toast("Link gerado com sucesso!")
            else:
                st.error("Erro ao gerar link.")

        if "url_ativa" in st.session_state:
            st.link_button("🔵 CLIQUE PARA PAGAR (MERCADO PAGO)", st.session_state.url_ativa, use_container_width=True)
            
            st.write("")

            if st.button("🔍 JÁ PAGUEI! VERIFICAR STATUS", use_container_width=True):
                with st.spinner("Consultando Mercado Pago..."):
                    try:
                        import orcas_v01_pagamentos as pag
                        from datetime import date
                        
                        # 1. CONSULTA DIRETA AO MERCADO PAGO (Via função no orcas_v01_pagamentos.py)
                        # confirmado_valor = pag.consultar_pagamento_mp(st.session_state.pref_id_ativa)
                        confirmado_valor = pag.consultar_pagamento_mp(ID_USUARIO_LOGADO)
                        
                        if confirmado_valor:
                            # 2. SE APROVADO, ATUALIZA O SUPABASE NA HORA
                            hoje = str(date.today())
                            supabase.table("usuarios").update({
                                "data_ult_assinat": hoje,
                                "valor_pago": confirmado_valor
                            }).eq("id", ID_USUARIO_LOGADO).execute()
                            
                            st.success(f"✅ Pagamento de R$ {confirmado_valor} Confirmado!")
                            st.balloons()
                            
                            # Limpa a URL da sessão para resetar o estado de pagamento
                            if "url_ativa" in st.session_state: 
                                del st.session_state.url_ativa
                            
                            st.rerun()
                        else:
                            st.warning("O Mercado Pago ainda não confirmou o recebimento. Se você já pagou, aguarde 30 segundos e tente novamente.")
                            
                    except Exception as e:
                        st.error(f"Erro na verificação direta: {e}")

    # Rodapé Integral
    st.markdown("""
    <div style="font-size: 12px; color: #333; margin-top: 20px; text-align: justify; line-height: 1.6; border-top: 1px solid #eee; padding-top: 10px;">
    Sua Assinatura ORCAS BABY mensal custa R$ 19,90 e contempla 2 Planos de 24 meses cada um, mas se você quiser ou necessitar, é possível aumentar o período de um Plano em blocos adicionais de 12 meses tendo um acréscimo de R$ 6,40 para cada 12 meses adicionais. Para aumentar o número de Planos (Padrão - 24 meses), o valor é de R$ 12,80 por Plano adicional. Para receber um Resumo Diário das análises e pendências como, o que preciso pagar e receber hoje, o que ainda está em aberto, quanto já gastei de supermercado até hoje, quanto já gastei nessa reforma, etc de seu Plano via Whatsapp ou E-mail terá um acréscimo de R$ 9,85 por Plano.
    </div>
    """, unsafe_allow_html=True)