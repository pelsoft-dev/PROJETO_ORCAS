import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def exibir_conciliacao(df, supabase, ID_USUARIO_LOGADO, format_moeda, parse_moeda):
    """
    Sub-rotina da Tela Conciliação - Versão com Scroll Mestre Sincronizado.
    """
    st.markdown(f'<div class="titulo-tela">Conciliação: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    # CSS PARA SCROLL SINCRONIZADO: Envolve todo o conteúdo em um bloco de largura fixa
    st.markdown("""
        <style>
        .container-mestre-scroll {
            width: 100%;
            overflow-x: auto !important;
            -webkit-overflow-scrolling: touch !important;
        }
        .bloco-tabela-concilia {
            min-width: 750px; /* Força a largura para que o scroll mova tudo junto */
            display: flex;
            flex-direction: column;
        }
        /* Garante que as colunas do Streamlit não quebrem linha dentro do container */
        .container-mestre-scroll [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
        }
        </style>
    """, unsafe_allow_html=True)

    hoje_c = datetime.now().date()
    ini_mes_c = hoje_c.replace(day=1)
    limite_c = hoje_c - timedelta(days=3)

    # Toggle alinhado à direita
    col_tit, col_tog = st.columns([5, 2])
    abrir_sem_plan = col_tog.toggle("Lançar sem Planejamento", value=st.session_state.get('abrir_sem_plan', False))
    st.session_state.abrir_sem_plan = abrir_sem_plan
    
    st.divider()

    # Lógica de lançamento sem planejamento (Mantida intacta)
    if st.session_state.abrir_sem_plan:
        cols_sp = st.columns([2.5, 1, 1.2, 1])
        sp_desc = cols_sp[0].text_input("Descrição", key="sp_desc", placeholder="Ex: Gasto Extra")
        sp_tipo = cols_sp[1].selectbox("E/S", ["Entrada", "Saída"], key="sp_tipo")
        sp_valor = cols_sp[2].text_input("Valor Real", key="sp_valor", value="0,00")
        
        with cols_sp[3]:
            st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
            btn_confirmar = st.button("Confirmar", key="btn_sp_conf", use_container_width=True)
        
        if btn_confirmar:
            v_sp = parse_moeda(sp_valor)
            if sp_desc and v_sp > 0:
                supabase.table("lancamentos").insert({
                    "projeto_id": str(st.session_state.projeto_ativo),
                    "usuario_id": str(ID_USUARIO_LOGADO),
                    "descricao": sp_desc,
                    "data": hoje_c.strftime('%Y-%m-%d'),
                    "data_vencimento": hoje_c.strftime('%Y-%m-%d'),
                    "tipo": sp_tipo,
                    "valor_plan": 0,
                    "valor_real": v_sp,
                    "status": "Realizado",
                    "parcial_real": 0,
                    "permite_parcial": False
                }).execute()
                st.session_state.abrir_sem_plan = False
                st.rerun()
        st.divider()

    df_c = df.copy()
    if not df_c.empty:
        df_c['dt_obj'] = pd.to_datetime(df_c['data']).dt.date
        
        df_f = df_c[
            (df_c['dt_obj'] <= hoje_c) & 
            (
                (df_c['status'] == 'Planejado') | 
                ((df_c['status'] == 'Realizado') & (df_c['dt_obj'] >= limite_c)) |
                ((df_c['valor_plan'] == 0) & (df_c['valor_real'] > 0))
            )
        ].copy()

        parciais_topo = df_f[(df_f['permite_parcial'] == True) & (df_f['dt_obj'] >= ini_mes_c)]
        demais_itens = df_f[~df_f.index.isin(parciais_topo.index)].sort_values('dt_obj', ascending=False)
        df_final_concilia = pd.concat([parciais_topo, demais_itens])

        # ABERTURA DO CONTAINER MESTRE DE ROLAGEM
        st.markdown('<div class="container-mestre-scroll"><div class="bloco-tabela-concilia">', unsafe_allow_html=True)

        # Cabeçalho (Agora dentro do scroll)
        h1, h2, h3, h4, h5, h6 = st.columns([2.5, 0.5, 1.2, 1.8, 1.8, 1.2])
        h1.write("**Data - Descrição**")
        h2.write("**E/S**")
        h3.write("**V. Plan.**")
        h4.write("**V. Real**")
        h5.write("**Valor Parcial**")
        h6.write("**Ação**")
        st.divider()

        for _, row in df_final_concilia.iterrows():
            v_acumulado_desc = df[df['descricao'] == row['descricao']]['parcial_real'].sum()
            cor_txt = "red" if (row['valor_plan'] > 0 and v_acumulado_desc > row['valor_plan']) else "black"
            
            st.markdown('<div style="margin-bottom: -38px;"></div>', unsafe_allow_html=True)
            c1, c2, c3, c4, c5, c6 = st.columns([2.5, 0.5, 1.2, 1.8, 1.8, 1.2])
            
            # FORMATO DE DATA PRESERVADO: DD/MM/AAAA
            c1.markdown(f"<span style='color:{cor_txt}'>{row['dt_obj'].strftime('%d/%m/%Y')} - {row['descricao']}</span>", unsafe_allow_html=True)
            cor_tipo = 'red' if row['tipo'] == 'Saída' else 'blue'
            c2.markdown(f"<span style='color:{cor_tipo}'>{row['tipo'][0]}</span>", unsafe_allow_html=True)
            
            if row['permite_parcial']:
                c3.markdown(f"<span style='color:{cor_txt}'>{format_moeda(row['valor_plan'])}</span>", unsafe_allow_html=True)
                c4.markdown(f"<span style='color:{cor_txt}'>{format_moeda(v_acumulado_desc)}</span>", unsafe_allow_html=True)
                
                v_key = f"v_p_{row['id']}"
                if v_key not in st.session_state:
                    st.session_state[v_key] = 0
                
                v_parc_in = c5.text_input("", key=f"p_{row['id']}_{st.session_state[v_key]}", value="0,00", label_visibility="collapsed")
                
                if c6.button("Confirmar", key=f"btn_p_{row['id']}", use_container_width=True):
                    v_dig = parse_moeda(v_parc_in)
                    if v_dig > 0:
                        supabase.table("lancamentos").insert({
                            "projeto_id": str(st.session_state.projeto_ativo),
                            "usuario_id": str(ID_USUARIO_LOGADO), 
                            "descricao": row['descricao'], 
                            "data": ini_mes_c.strftime('%Y-%m-%d'), 
                            "data_vencimento": ini_mes_c.strftime('%Y-%m-%d'), 
                            "tipo": row['tipo'],
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
                    if c6.button("Confirmar", key=f"btn_n_{row['id']}", use_container_width=True):
                        v_para_gravar = parse_moeda(v_norm_in)
                        if v_para_gravar == 0:
                            v_para_gravar = row['valor_plan']
                            
                        supabase.table("lancamentos").update({
                            "valor_real": v_para_gravar, 
                            "status": "Realizado"
                        }).eq("id", row['id']).execute()
                        st.rerun()
            st.divider()

        # FECHAMENTO DO CONTAINER MESTRE
        st.markdown('</div></div>', unsafe_allow_html=True)
    else:
        st.info("Nenhum lançamento pendente para conciliação.")