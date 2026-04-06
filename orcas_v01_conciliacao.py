import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def exibir_conciliacao(df, supabase, ID_USUARIO_LOGADO, format_moeda, parse_moeda):
    """
    Sub-rotina da Tela Conciliação - Rigor total na exibição horizontal e lógica de dados.
    """
    st.markdown(f'<div class="titulo-tela">Conciliação: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    # CSS Injetado para garantir o comportamento de tabela única com scroll
    st.markdown("""
        <style>
        .scroll-area { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 20px; }
        .tab-conc { border-collapse: collapse; min-width: 650px; width: 100%; font-family: sans-serif; }
        .tab-conc th { background: #f8f9fa; border-top: 1px solid #ddd; border-bottom: 2px solid #eee; padding: 10px 5px; text-align: left; font-size: 0.85rem; }
        .tab-conc td { border-bottom: 1px solid #eee; padding: 8px 5px; vertical-align: middle; font-size: 0.85rem; }
        .col-fix-dt { width: 180px; }
        .col-fix-es { width: 30px; text-align: center; }
        .col-fix-val { width: 90px; text-align: right; }
        .col-fix-inp { width: 120px; }
        .col-fix-btn { width: 80px; text-align: center; }
        </style>
    """, unsafe_allow_html=True)

    hoje_c = datetime.now().date()
    ini_mes_c = hoje_c.replace(day=1)
    limite_c = hoje_c - timedelta(days=3)

    col_tit, col_tog = st.columns([5, 2])
    abrir_sem_plan = col_tog.toggle("Lançar sem Planejamento", value=st.session_state.get('abrir_sem_plan', False))
    st.session_state.abrir_sem_plan = abrir_sem_plan
    
    st.divider()

    if st.session_state.abrir_sem_plan:
        cols_sp = st.columns([2.5, 1, 1.2, 1])
        sp_desc = cols_sp[0].text_input("Descrição", key="sp_desc", placeholder="Ex: Gasto Extra")
        sp_tipo = cols_sp[1].selectbox("E/S", ["Entrada", "Saída"], key="sp_tipo")
        sp_valor = cols_sp[2].text_input("Valor Real", key="sp_valor", value="0,00")
        with cols_sp[3]:
            st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
            if st.button("Confirmar", key="btn_sp_conf", use_container_width=True):
                v_sp = parse_moeda(sp_valor)
                if sp_desc and v_sp > 0:
                    supabase.table("lancamentos").insert({
                        "projeto_id": str(st.session_state.projeto_ativo),
                        "usuario_id": str(ID_USUARIO_LOGADO),
                        "descricao": sp_desc,
                        "data": hoje_c.strftime('%Y-%m-%d'),
                        "data_vencimento": hoje_c.strftime('%Y-%m-%d'),
                        "tipo": sp_tipo,
                        "valor_plan": 0, "valor_real": v_sp,
                        "status": "Realizado", "parcial_real": 0, "permite_parcial": False
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

        # Renderização da Tabela de Conciliação
        # Usamos colunas nativas dentro de um bloco HTML para manter a funcionalidade dos inputs
        st.markdown('<div class="scroll-area">', unsafe_allow_html=True)
        
        # Cabeçalho Fixo
        h1, h2, h3, h4, h5, h6 = st.columns([2.5, 0.5, 1.2, 1.8, 1.8, 1.2])
        h1.write("**Data - Descrição**")
        h2.write("**E/S**")
        h3.write("**V. Plan.**")
        h4.write("**V. Real**")
        h5.write("**V. Parcial**")
        h6.write("**Ação**")
        st.divider()

        for _, row in df_final_concilia.iterrows():
            v_acumulado_desc = df[df['descricao'] == row['descricao']]['parcial_real'].sum()
            cor_txt = "red" if (row['valor_plan'] > 0 and v_acumulado_desc > row['valor_plan']) else "black"
            
            # Container de linha para evitar quebra no mobile
            with st.container():
                st.markdown('<div style="margin-bottom: -35px;"></div>', unsafe_allow_html=True)
                c1, c2, c3, c4, c5, c6 = st.columns([2.5, 0.5, 1.2, 1.8, 1.8, 1.2])
                
                c1.markdown(f"<span style='color:{cor_txt}'>{row['dt_obj'].strftime('%d/%m/%Y')} - {row['descricao']}</span>", unsafe_allow_html=True)
                cor_tipo = 'red' if row['tipo'] == 'Saída' else 'blue'
                c2.markdown(f"<span style='color:{cor_tipo}'>{row['tipo'][0]}</span>", unsafe_allow_html=True)
                
                if row['permite_parcial']:
                    c3.markdown(f"<span style='color:{cor_txt}'>{format_moeda(row['valor_plan'])}</span>", unsafe_allow_html=True)
                    c4.markdown(f"<span style='color:{cor_txt}'>{format_moeda(v_acumulado_desc)}</span>", unsafe_allow_html=True)
                    
                    v_key = f"v_p_{row['id']}"
                    if v_key not in st.session_state: st.session_state[v_key] = 0
                    
                    v_parc_in = c5.text_input("", key=f"p_{row['id']}_{st.session_state[v_key]}", value="0,00", label_visibility="collapsed")
                    
                    if c6.button("Confirmar", key=f"btn_p_{row['id']}", use_container_width=True):
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
                        if c6.button("Confirmar", key=f"btn_n_{row['id']}", use_container_width=True):
                            v_para_gravar = parse_moeda(v_norm_in)
                            if v_para_gravar == 0: v_para_gravar = row['valor_plan']
                            supabase.table("lancamentos").update({"valor_real": v_para_gravar, "status": "Realizado"}).eq("id", row['id']).execute()
                            st.rerun()
                st.divider()
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("Nenhum lançamento pendente para conciliação.")