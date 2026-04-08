import streamlit as st
import pandas as pd
import plotly.graph_objects as go

def exibir_dashboard(df, supabase, ID_USUARIO_LOGADO, s_db):
    """
    Sub-rotina da Tela Dashboard - Mantida integralmente conforme lógica original.
    """
    st.markdown(f'<div class="titulo-tela">Dashboard: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    if not df.empty and 'data' in df.columns:
        # Converter data para objeto datetime
        df['dt'] = pd.to_datetime(df['data'])
        
        # AJUSTE: Soma valor_real e parcial_real. Como o pai tem parcial_real=0 
        # e os filhos têm valor_real=0, a soma simples evita duplicidade e pega tudo > 0.
        df['v_real_full'] = df['valor_real'] + df['parcial_real']
        
        # Lógica de sinal para saldo acumulado
        df['v'] = df.apply(
            lambda x: (x['v_real_full'] if (x['status'] == 'Realizado' or x['v_real_full'] > 0) else x['valor_plan']) * (1 if x['tipo'] == 'Entrada' else -1), 
            axis=1
        )
        
        # Agrupamento diário para o gráfico de linha
        df_diario = df.groupby('dt')['v'].sum().reset_index()
        df_diario = df_diario.sort_values('dt')
        df_diario['Saldo Acumulado'] = df_diario['v'].cumsum() + s_db
        
        # Gráfico de Evolução de Saldo
        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(
            x=df_diario['dt'], 
            y=df_diario['Saldo Acumulado'], 
            mode='lines', 
            name='Saldo', 
            line=dict(color='#1E3A8A', width=3), 
            fill='tozeroy', 
            fillcolor='rgba(30, 58, 138, 0.1)'
        ))
        
        fig_line.update_layout(
            title="Evolução do Saldo Projetado/Realizado", 
            height=350, 
            margin=dict(l=20, r=20, t=50, b=20), 
            hovermode="x unified"
        )
        st.plotly_chart(fig_line, use_container_width=True)
        
        # Análise Mensal
        st.subheader("Análise Mensal: Planejado x Realizado")
        df['MesAno'] = df['dt'].dt.strftime('%b/%y')
        
        # AGREGAÇÃO: Soma o planejado e a nova coluna que consolida qualquer valor realizado > 0
        res_mensal = df.groupby(['MesAno', 'tipo']).agg({'valor_plan':'sum', 'v_real_full':'sum'}).reset_index()
        res_mensal.rename(columns={'v_real_full': 'valor_real'}, inplace=True)
        
        meses_ordem = df.sort_values('dt')['MesAno'].unique()
        
        # Gráfico de Barras Planejado x Realizado
        fig_bar = go.Figure()
        cores_map = {
            'Entrada': {'p': '#A5D8FF', 'r': '#1E3A8A'}, 
            'Saída': {'p': '#FFA8A8', 'r': '#C53030'}
        }
        
        for tipo_mov in ['Entrada', 'Saída']:
            d_tipo = res_mensal[res_mensal['tipo'] == tipo_mov]
            if not d_tipo.empty:
                fig_bar.add_trace(go.Bar(
                    x=d_tipo['MesAno'], 
                    y=d_tipo['valor_plan'], 
                    name=f'{tipo_mov} Plan.', 
                    marker_color=cores_map[tipo_mov]['p'], 
                    offsetgroup=tipo_mov, 
                    width=0.3
                ))
                fig_bar.add_trace(go.Bar(
                    x=d_tipo['MesAno'], 
                    y=d_tipo['valor_real'], 
                    name=f'{tipo_mov} Real.', 
                    marker_color=cores_map[tipo_mov]['r'], 
                    offsetgroup=tipo_mov, 
                    width=0.15
                ))
        
        fig_bar.update_layout(
            barmode='group', 
            xaxis={'categoryorder':'array', 'categoryarray':meses_ordem}, 
            height=350
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("💡 Nenhum dado encontrado para gerar o Dashboard.")