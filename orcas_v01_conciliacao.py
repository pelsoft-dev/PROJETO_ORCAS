import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def exibir_conciliacao(df, supabase, ID_USUARIO_LOGADO, format_moeda, parse_moeda):
    """
    Sub-rotina da Tela Conciliação - Scroll Sincronizado via CSS Injection.
    """
    st.markdown(f'<div class="titulo-tela">Conciliação: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    # INJEÇÃO DE CSS DE ALTO RIGOR
    st.markdown("""
        <style>
        /* Container principal da página para permitir o scroll do conjunto */
        [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
            overflow-x: auto !important;
            display: block !important;
            -webkit-overflow-scrolling: touch !important;
        }
        /* Força as colunas a manterem largura mínima e não empilharem */
        [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            min-width: 750px !important;
            margin-bottom: 0px !important;
        }
        /* REDUÇÃO AGRESSIVA DE ALTURAS CONFORME SOLICITADO NO ANEXO */
        [data-testid="stVerticalBlock"] {
            gap: 0rem !important;
        }
        .stElementContainer {
            margin-bottom: -1.3rem !important;
        }
        hr {
            margin-top: 0.4rem !important;
            margin-bottom: 0.4rem !important;
        }
        /* Garante que os inputs não fiquem espremidos */
        [data-testid="column"] {
            flex-shrink: 0 !important;
            min-width: 50px !important;
        }
        /* Ajuste para que os labels dos toggles não quebrem e alinhem conforme solicitado */
        [data-testid="column"] .stWidgetLabel {
            white-space: nowrap !important;
            min-width: fit-content !important;
        }
        /* Estilização da mensagem de orientação */
        .msg-orientacao {
            font-size: 0.85rem;
            color: #555;
            display: flex;
            align-items: center;
            height: 100%;
        }
        </style>
    """, unsafe_allow_html=True)

    hoje_c = datetime.now().date()
    ini_mes_c = hoje_c.replace(day=1)
    limite_c = hoje_c - timedelta(days=3)

    # LINHA DE COMANDO - PROPORÇÃO AJUSTADA PARA [4, 3] PARA TRAZER TOGGLES MAIS À ESQUERDA
    col_aviso, col_tog = st.columns([4, 3])
    
    col_aviso.markdown('<div class="msg-orientacao">📱🔄 SE USANDO O CELULAR, TRABALHE COM ELE NA HORIZONTAL</div>', unsafe_allow_html=True)
    
    # Toggles de Controle
    abrir_sem_plan = col_tog.toggle("Lançar sem Planejamento", value=st.session_state.get('abrir_sem_plan', False))
    st.session_state.abrir_sem_plan = abrir_sem_plan
    
    listar_todos_mes = col_tog.toggle("Listar todos Lançamentos do mês", value=st.session_state.get('listar_todos_mes', False))
    st.session_state.listar_todos_mes = listar_todos_mes
    
    st.divider()

    if st.session_state.abrir_sem_plan:
        cols_sp = st.columns([2.5, 1, 1.2, 1])
        sp_desc = cols_sp[0].text_input("Descrição", key="sp_desc", placeholder="Ex: Gasto Extra")
        sp_tipo = cols_sp[1].selectbox("E/S", ["Entrada", "Saída"], key="sp_tipo")
        sp_valor = cols_sp[2].text_input("Valor Real", key="sp_valor", value="0,00")
        
        with cols_sp[3]:
            st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
            btn_confirmar = st.button("OK", key="btn_sp_conf", use_container_width=True)
        
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
                    "valor_plan": 0, "valor_real": v_sp,
                    "status": "Realizado", "parcial_real": 0, "permite_parcial": False
                }).execute()
                st.session_state.abrir_sem_plan = False
                st.rerun()
        st.divider()

    df_c = df.copy()
    if not df_c.empty:
        df_c['dt_obj'] = pd.to_datetime(df_c['data']).dt.date
        
        # LÓGICA DE FILTRO: LISTAR TUDO DO MÊS (EXCLUINDO PARCIAIS) OU CONCILIAÇÃO PADRÃO
        if st.session_state.listar_todos_mes:
            proximo_mes = (ini_mes_c + timedelta(days=32)).replace(day=1)
            fim_mes_c = proximo_mes - timedelta(days=1)
            # REGRA APLICADA: registros com parcial_real > 0 NÃO devem ser listados nesta função
            df_f = df_c[(df_c['dt_obj'] >= ini_mes_c) & (df_c['dt_obj'] <= fim_mes_c) & (df_c['parcial_real'] == 0)].copy()
        else:
            df_f = df_c[(df_c['dt_obj'] <= hoje_c) & ((df_c['status'] == 'Planejado') | ((df_c['status'] == 'Realizado') & (df_c['dt_obj'] >= limite_c)) | ((df_c['valor_plan'] == 0) & (df_c['valor_real'] > 0)))].copy()
        
        parciais_topo = df_f[(df_f['permite_parcial'] == True) & (df_f['dt_obj'] >= ini_mes_c)]
        demais_itens = df_f[~df_f.index.isin(parciais_topo.index)].sort_values('dt_obj', ascending=False)
        df_final_concilia = pd.concat([parciais_topo, demais_itens])

        # Cabeçalho - LARGURAS AJUSTADAS CONFORME ANEXO: [2.2, 0.5, 1.2, 1.2, 1.2, 0.5]
        h1, h2, h3, h4, h5, h6 = st.columns([2.2, 0.5, 1.2, 1.2, 1.2, 0.5])
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
            
            # AJUSTE DE MARGEM PARA REDUZIR ALTURA PELA METADE (-32px conforme necessidade do layout)
            st.markdown('<div style="margin-bottom: -32px;"></div>', unsafe_allow_html=True)
            
            # COLUNAS DO ITEM - LARGURAS AJUSTADAS: [2.2, 0.5, 1.2, 1.2, 1.2, 0.5]
            c1, c2, c3, c4, c5, c6 = st.columns([2.2, 0.5, 1.2, 1.2, 1.2, 0.5])
            
            c1.markdown(f"<span style='color:{cor_txt}'>{row['dt_obj'].strftime('%d/%m/%Y')} - {row['descricao']}</span>", unsafe_allow_html=True)
            cor_tipo = 'red' if row['tipo'] == 'Saída' else 'blue'
            c2.markdown(f"<span style='color:{cor_tipo}'>{row['tipo'][0]}</span>", unsafe_allow_html=True)
            
            if row['permite_parcial']:
                c3.markdown(f"<span style='color:{cor_txt}'>{format_moeda(row['valor_plan'])}</span>", unsafe_allow_html=True)
                c4.markdown(f"<span style='color:{cor_txt}'>{format_moeda(v_acumulado_desc)}</span>", unsafe_allow_html=True)
                
                v_key = f"v_p_{row['id']}"
                if v_key not in st.session_state: st.session_state[v_key] = 0
                v_parc_in = c5.text_input("", key=f"p_{row['id']}_{st.session_state[v_key]}", value="0,00", label_visibility="collapsed")
                
                if c6.button("OK", key=f"btn_p_{row['id']}", use_container_width=True):
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
                    if c6.button("OK", key=f"btn_n_{row['id']}", use_container_width=True):
                        v_para_gravar = parse_moeda(v_norm_in)
                        if v_para_gravar == 0: v_para_gravar = row['valor_plan']
                        supabase.table("lancamentos").update({"valor_real": v_para_gravar, "status": "Realizado"}).eq("id", row['id']).execute()
                        st.rerun()
            st.divider()
    else:
        st.info("Nenhum lançamento pendente para conciliação.")