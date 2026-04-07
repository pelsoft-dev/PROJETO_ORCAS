import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def exibir_conciliacao(df, supabase, ID_USUARIO_LOGADO, format_moeda, parse_moeda):
    """
    Sub-rotina da Tela Conciliação - Foco em Densidade Mobile e Aviso de Orientação.
    """
    st.markdown(f'<div class="titulo-tela">Conciliação: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    # CSS DE ALTO RIGOR PARA DENSIDADE E SCROLL
    st.markdown("""
        <style>
        /* Força o scroll horizontal no container principal */
        [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
            overflow-x: auto !important;
            display: block !important;
            -webkit-overflow-scrolling: touch !important;
        }
        /* REMOVE O ESPAÇAMENTO (GAP) ENTRE COLUNAS PARA CELULAR */
        [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            min-width: 680px !important; 
            gap: 0.5rem !important; /* Diminui o buraco entre os campos */
        }
        /* Ajuste fino das larguras para colar os dados */
        [data-testid="column"] {
            flex-shrink: 0 !important;
            min-width: 40px !important;
            padding: 0px 2px !important; /* Remove respiros laterais inúteis */
        }
        [data-testid="column"]:nth-child(1) { min-width: 200px !important; } /* Data-Desc */
        [data-testid="column"]:nth-child(2) { min-width: 30px !important; }  /* E/S */
        [data-testid="column"]:nth-child(3) { min-width: 85px !important; }  /* V.Plan */
        [data-testid="column"]:nth-child(4) { min-width: 105px !important; } /* V.Real */
        [data-testid="column"]:nth-child(5) { min-width: 105px !important; } /* V.Parcial */
        [data-testid="column"]:nth-child(6) { min-width: 90px !important; }  /* Ação */

        /* Estilo para o aviso de celular */
        .aviso-mobile {
            color: #666;
            font-size: 0.8rem;
            font-style: italic;
            display: flex;
            align-items: center;
            height: 100%;
        }
        </style>
    """, unsafe_allow_html=True)

    hoje_c = datetime.now().date()
    ini_mes_c = hoje_c.replace(day=1)
    limite_c = hoje_c - timedelta(days=3)

    # LINHA DE COMANDO: MENSAGEM À ESQUERDA + TOGGLE À DIREITA
    col_aviso, col_tog = st.columns([1.5, 1])
    
    # Mensagem de orientação sugerida
    col_aviso.markdown('<div class="aviso-mobile">📱 Aconselha-se utilizar o celular deitado</div>', unsafe_allow_html=True)
    
    abrir_sem_plan = col_tog.toggle("Lançar sem Planejamento", value=st.session_state.get('abrir_sem_plan', False))
    st.session_state.abrir_sem_plan = abrir_sem_plan
    
    st.divider()

    # Lógica de lançamento extra (Mantida)
    if st.session_state.abrir_sem_plan:
        cols_sp = st.columns([2, 0.8, 1, 1])
        sp_desc = cols_sp[0].text_input("Descrição", key="sp_desc")
        sp_tipo = cols_sp[1].selectbox("E/S", ["Entrada", "Saída"], key="sp_tipo")
        sp_valor = cols_sp[2].text_input("Valor Real", key="sp_valor", value="0,00")
        with cols_sp[3]:
            st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
            if st.button("OK", key="btn_sp_conf", use_container_width=True):
                v_sp = parse_moeda(sp_valor)
                if sp_desc and v_sp > 0:
                    supabase.table("lancamentos").insert({
                        "projeto_id": str(st.session_state.projeto_ativo),
                        "usuario_id": str(ID_USUARIO_LOGADO),
                        "descricao": sp_desc, "data": hoje_c.strftime('%Y-%m-%d'),
                        "data_vencimento": hoje_c.strftime('%Y-%m-%d'), "tipo": sp_tipo,
                        "valor_plan": 0, "valor_real": v_sp, "status": "Realizado",
                        "parcial_real": 0, "permite_parcial": False
                    }).execute()
                    st.session_state.abrir_sem_plan = False
                    st.rerun()
        st.divider()

    df_c = df.copy()
    if not df_c.empty:
        df_c['dt_obj'] = pd.to_datetime(df_c['data']).dt.date
        df_f = df_c[(df_c['dt_obj'] <= hoje_c) & ((df_c['status'] == 'Planejado') | ((df_c['status'] == 'Realizado') & (df_c['dt_obj'] >= limite_c)) | ((df_c['valor_plan'] == 0) & (df_c['valor_real'] > 0)))].copy()
        
        parciais_topo = df_f[(df_f['permite_parcial'] == True) & (df_f['dt_obj'] >= ini_mes_c)]
        demais_itens = df_f[~df_f.index.isin(parciais_topo.index)].sort_values('dt_obj', ascending=False)
        df_final_concilia = pd.concat([parciais_topo, demais_itens])

        # Cabeçalho da Tabela
        h1, h2, h3, h4, h5, h6 = st.columns([2.5, 0.4, 1.2, 1.5, 1.5, 1.2])
        h1.write("**Data/Desc**")
        h2.write("**E/S**")
        h3.write("**V.Plan**")
        h4.write("**V.Real**")
        h5.write("**V.Parc**")
        h6.write("**Ação**")
        st.divider()

        for _, row in df_final_concilia.iterrows():
            v_acumulado_desc = df[df['descricao'] == row['descricao']]['parcial_real'].sum()
            cor_txt = "red" if (row['valor_plan'] > 0 and v_acumulado_desc > row['valor_plan']) else "black"
            
            # Margem negativa para compactar verticalmente
            st.markdown('<div style="margin-bottom: -38px;"></div>', unsafe_allow_html=True)
            c1, c2, c3, c4, c5, c6 = st.columns([2.5, 0.4, 1.2, 1.5, 1.5, 1.2])
            
            # Dados com formatação preservada
            c1.markdown(f"<span style='color:{cor_txt}; font-size:0.85rem'>{row['dt_obj'].strftime('%d/%m')} - {row['descricao']}</span>", unsafe_allow_html=True)
            cor_tipo = 'red' if row['tipo'] == 'Saída' else 'blue'
            c2.markdown(f"<span style='color:{cor_tipo}'>{row['tipo'][0]}</span>", unsafe_allow_html=True)
            
            if row['permite_parcial']:
                c3.markdown(f"<span style='font-size:0.85rem'>{format_moeda(row['valor_plan'])}</span>", unsafe_allow_html=True)
                c4.markdown(f"<span style='font-size:0.85rem'>{format_moeda(v_acumulado_desc)}</span>", unsafe_allow_html=True)
                
                v_key = f"v_p_{row['id']}"
                if v_key not in st.session_state: st.session_state[v_key] = 0
                v_parc_in = c5.text_input("", key=f"p_{row['id']}_{st.session_state[v_key]}", value="0,00", label_visibility="collapsed")
                
                if c6.button("Conf", key=f"btn_p_{row['id']}", use_container_width=True):
                    v_dig = parse_moeda(v_parc_in)
                    if v_dig > 0:
                        supabase.table("lancamentos").insert({
                            "projeto_id": str(st.session_state.projeto_ativo),
                            "usuario_id": str(ID_USUARIO_LOGADO), 
                            "descricao": row['descricao'], "data": ini_mes_c.strftime('%Y-%m-%d'), 
                            "data_vencimento": ini_mes_c.strftime('%Y-%m-%d'), "tipo": row['tipo'],
                            "valor_plan": 0, "valor_real": 0, "status": "Realizado",
                            "parcial_real": v_dig, "parcial_data": hoje_c.strftime('%Y-%m-%d'), "permite_parcial": False
                        }).execute()
                        st.session_state[v_key] += 1
                        st.rerun()
            else:
                c3.write(format_moeda(row['valor_plan']))
                if row['status'] == 'Realizado':
                    c4.write(format_moeda(row['valor_real']))
                    c6.write("✅")
                else:
                    v_norm_in = c4.text_input("", key=f"n_{row['id']}", value="0,00", label_visibility="collapsed")
                    if c6.button("Conf", key=f"btn_n_{row['id']}", use_container_width=True):
                        v_pg = parse_moeda(v_norm_in)
                        if v_pg == 0: v_pg = row['valor_plan']
                        supabase.table("lancamentos").update({"valor_real": v_pg, "status": "Realizado"}).eq("id", row['id']).execute()
                        st.rerun()
            st.divider()
    else:
        st.info("Nenhum lançamento pendente.")