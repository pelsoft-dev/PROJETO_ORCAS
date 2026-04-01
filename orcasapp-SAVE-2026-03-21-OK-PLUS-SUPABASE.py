import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import hashlib
import plotly.graph_objects as go
import streamlit.components.v1 as components
from supabase import Client

# --- 1. SEGURANÇA E CONEXÃO ---
try:
    import orcas_v01_security as security
    supabase: Client = security.supabase
except Exception as e:
    st.error(f"Erro de conexão: Verifique o arquivo security.py e sua conexão. {e}")
    st.stop()

# --- 2. CONFIGURAÇÃO E ESTILO ---
st.set_page_config(page_title="ORCAS - Gestão Financeira", layout="wide", initial_sidebar_state="expanded")

def ir_para_o_topo():
    components.html("""<script>window.parent.document.getElementById('topo-ancora').scrollIntoView();</script>""", height=0)

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    [data-testid="stHeader"] {background: rgba(0,0,0,0) !important; color: transparent !important;}
    .block-container { padding-top: 0.1rem !important; }
    .logo-sidebar { font-size: 2.2rem !important; font-weight: bold; color: #1E3A8A; font-family: 'Arial Black', sans-serif; }
    .user-email { font-size: 0.85rem; color: #64748b; margin-bottom: 2px; }
    .venc-text { font-size: 0.8rem; color: #e11d48; font-weight: bold; margin-bottom: 10px; }
    .titulo-tela { font-size: 1.6rem; font-weight: bold; color: #1E3A8A; border-bottom: 2px solid #E5E7EB; margin-bottom: 15px; padding-bottom: 5px; }
    .project-tag-sidebar { color: #1E3A8A; font-weight: bold; font-size: 0.9rem; margin-bottom: 15px; padding: 8px; border-left: 5px solid #1E3A8A; background: #F3F4F6; border-radius: 4px; }
    div[data-testid="column"] button { width: 100% !important; }
    .info-pagamento { background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; margin-top: 10px; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

def format_moeda(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def parse_moeda(t):
    try:
        t = str(t).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        return float(t)
    except:
        return 0.0

# --- 3. LOGIN ---
if 'logado' not in st.session_state:
    st.session_state.logado = False

if not st.session_state.logado:
    st.markdown("<h1 style='text-align: center; margin-top: 50px;'>🐋 ORCAS</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        aba = st.tabs(["Acessar Conta", "Criar Nova Conta"])
        with aba[0]:
            em = st.text_input("E-mail Cadastrado")
            se = st.text_input("Senha de Acesso", type="password")
            if st.button("Entrar no Sistema"):
                senha_hash = hashlib.sha256(str.encode(se)).hexdigest()
                # CORREÇÃO: Removida a coluna 'telefone' para evitar o erro de coluna inexistente (Anexo b8acc6)
                res = supabase.table("usuarios").select("id, vencimento, zap_ativo").eq("email", em).eq("senha", senha_hash).execute()
                if res.data: 
                    user_data = res.data[0]
                    st.session_state.logado = True
                    st.session_state.user_id = user_data['id']
                    st.session_state.usuario = em
                    st.session_state.vencimento = str(user_data['vencimento'])
                    st.session_state.zap_ativo = user_data.get('zap_ativo', 0)
                    st.session_state.projeto_ativo = None
                    st.rerun()
                else:
                    st.error("E-mail ou senha incorretos.")
        with aba[1]:
            st.info("Para criar uma nova conta, entre em contato com o suporte administrativo do ORCAS.")
    st.stop()
    # --- 4. ESTADO E DADOS ---
uid = st.session_state.user_id
venc_dt = datetime.strptime(st.session_state.vencimento, '%Y-%m-%d').date()
dias_rest = (venc_dt - datetime.now().date()).days
security.verificar_bloqueio_v01(uid, dias_rest)

# Recupera lista de projetos do usuário
projs_req = supabase.table("config_projetos").select("projeto_id").eq("usuario_id", uid).execute()
projs = [r['projeto_id'] for r in projs_req.data]

if 'projeto_ativo' not in st.session_state:
    st.session_state.projeto_ativo = None
if 'msg_sucesso' not in st.session_state:
    st.session_state.msg_sucesso = None
if 'confirmar_exclusao_ativa' not in st.session_state:
    st.session_state.confirmar_exclusao_ativa = False

# Valores padrão de data e saldo
s_db = 0.0
d_ini_db = datetime.now().date()
d_fim_db = (datetime.now() + timedelta(days=730)).date()

if st.session_state.projeto_ativo:
    cfg_req = supabase.table("config_projetos").select("*").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).execute()
    if cfg_req.data:
        cfg = cfg_req.data[0]
        s_db = cfg.get('saldo_inicial', 0.0)
        d_ini_db = datetime.strptime(cfg['data_ini'], '%Y-%m-%d').date()
        d_fim_db = datetime.strptime(cfg['data_fim'], '%Y-%m-%d').date()

# --- 5. BARRA LATERAL ---
with st.sidebar:
    st.markdown('<div class="logo-sidebar">🐋 ORCAS</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="user-email">👤 {st.session_state.usuario}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="venc-text">⏳ {max(0, dias_rest)} DIAS RESTANTES</div>', unsafe_allow_html=True)
    
    if st.session_state.projeto_ativo:
        st.markdown(f'<div class="project-tag-sidebar">Fluxo Ativo: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
        
        # Ajuste de Saldo Inicial com Upsert corrigido (Anexo c581c7)
        n_saldo_txt = st.text_input("Saldo Inicial", value=format_moeda(s_db))
        n_saldo_val = parse_moeda(n_saldo_txt)
        
        if n_saldo_val != s_db:
            dados_upsert = {
                "projeto_id": st.session_state.projeto_ativo,
                "usuario_id": uid,
                "saldo_inicial": n_saldo_val,
                "data_ini": d_ini_db.strftime('%Y-%m-%d'),
                "data_fim": d_fim_db.strftime('%Y-%m-%d')
            }
            # Busca ID existente para evitar erro de duplicate key no Supabase
            check_exist = supabase.table("config_projetos").select("id").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).execute()
            if check_exist.data:
                dados_upsert["id"] = check_exist.data[0]["id"]
            
            supabase.table("config_projetos").upsert(dados_upsert).execute()
            st.rerun()

    st.divider()
    menu_opcoes = ["🏠 Dashboard", "📑 Lançamentos", "📅 Projetar", "✅ Conciliação", "⚙️ Gestão"]
    # Se não houver projeto ativo, força a aba Gestão para o usuário criar/selecionar um
    idx_default = 4 if st.session_state.projeto_ativo is None else 0
    escolha = st.radio("Navegação", menu_opcoes, index=idx_default, label_visibility="collapsed")
    
    st.divider()
    if st.button("Sair do Sistema"):
        st.session_state.clear()
        st.rerun()

# Âncora para retorno ao topo
st.markdown("<div id='topo-ancora'></div>", unsafe_allow_html=True)
if st.session_state.projeto_ativo is None:
    escolha = "⚙️ Gestão"
    # --- 6. CARREGAMENTO DO DATAFRAME (BLINDAGEM CONTRA ERROS DE COLUNA) ---
# Busca todos os lançamentos do projeto ativo
res_l = supabase.table("lancamentos").select("*").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).order("data").execute()
df = pd.DataFrame(res_l.data)

if not df.empty:
    # CORREÇÃO: Força colunas minúsculas para o Pandas encontrar 'data' independente do banco (Anexo b8cb9e)
    df.columns = [c.lower() for c in df.columns]
else:
    # Garante que o DF tenha as colunas mínimas para não quebrar a lógica abaixo
    df = pd.DataFrame(columns=['id', 'data', 'descricao', 'tipo', 'valor_plan', 'valor_real', 'status'])

# --- TELA: DASHBOARD ---
if escolha == "🏠 Dashboard":
    st.markdown(f'<div class="titulo-tela">Dashboard: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    if not df.empty and 'data' in df.columns:
        # Conversão e Cálculos
        df['dt'] = pd.to_datetime(df['data'])
        df['v'] = df.apply(lambda x: (x['valor_real'] if x['status'] == 'Realizado' else x['valor_plan']) * (1 if x['tipo'] == 'Entrada' else -1), axis=1)
        
        # Agrupamento por data para o gráfico de linha
        df_diario = df.groupby('dt')['v'].sum().reset_index()
        df_diario['Saldo Acumulado'] = df_diario['v'].cumsum() + s_db
        
        # Gráfico 1: Evolução do Saldo
        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(
            x=df_diario['dt'], 
            y=df_diario['Saldo Acumulado'], 
            mode='lines', 
            name='Saldo Disponível',
            line=dict(color='#1E3A8A', width=3),
            fill='tozeroy',
            fillcolor='rgba(30, 58, 138, 0.1)'
        ))
        fig_line.update_layout(
            title="Evolução do Saldo Projetado",
            xaxis_title="Período",
            yaxis_title="Valor (R$)",
            height=350,
            margin=dict(l=20, r=20, t=50, b=20),
            hovermode="x unified"
        )
        st.plotly_chart(fig_line, use_container_width=True)
        
        # Gráfico 2: Planejado x Realizado Mensal
        st.subheader("Análise Mensal: Planejado x Realizado")
        df['MesAno'] = df['dt'].dt.strftime('%b/%y')
        res_mensal = df.groupby(['MesAno', 'tipo']).agg({'valor_plan':'sum', 'valor_real':'sum'}).reset_index()
        
        # Ordenação cronológica para o gráfico de barras
        meses_ordem = df.sort_values('dt')['MesAno'].unique()
        
        fig_bar = go.Figure()
        cores_map = {
            'Entrada': {'p': '#A5D8FF', 'r': '#1E3A8A'}, 
            'Saída': {'p': '#FFA8A8', 'r': '#C53030'}
        }
        
        for tipo_mov in ['Entrada', 'Saída']:
            d_tipo = res_mensal[res_mensal['tipo'] == tipo_mov]
            if not d_tipo.empty:
                # Barra Planejado (mais clara)
                fig_bar.add_trace(go.Bar(
                    x=d_tipo['MesAno'], y=d_tipo['valor_plan'],
                    name=f'{tipo_mov} Planejado',
                    marker_color=cores_map[tipo_mov]['p'],
                    offsetgroup=tipo_mov,
                    width=0.3
                ))
                # Barra Realizado (mais escura)
                fig_bar.add_trace(go.Bar(
                    x=d_tipo['MesAno'], y=d_tipo['valor_real'],
                    name=f'{tipo_mov} Realizado',
                    marker_color=cores_map[tipo_mov]['r'],
                    offsetgroup=tipo_mov,
                    width=0.15
                ))
        
        fig_bar.update_layout(
            barmode='group',
            xaxis={'categoryorder':'array', 'categoryarray':meses_ordem},
            margin=dict(l=20, r=20, t=20, b=20),
            height=350
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("💡 Nenhum dado encontrado para este fluxo. Comece projetando seus lançamentos!")
        # --- TELA: LANÇAMENTOS ---
elif escolha == "📑 Lançamentos":
    st.markdown(f'<div class="titulo-tela">Lançamentos: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    # Gerar lista de meses entre data_ini e data_fim para o loop
    meses_periodo = []
    data_atual_loop = d_ini_db.replace(day=1)
    
    while data_atual_loop <= d_fim_db:
        meses_periodo.append(data_atual_loop.strftime('%Y-%m'))
        # Avança para o próximo mês
        if data_atual_loop.month == 12:
            data_atual_loop = data_atual_loop.replace(year=data_atual_loop.year + 1, month=1)
        else:
            data_atual_loop = data_atual_loop.replace(month=data_atual_loop.month + 1)
    
    # Variável para carregar o saldo acumulado entre os meses
    saldo_acumulado_mes = s_db
    
    if not meses_periodo:
        st.warning("⚠️ O período do fluxo não está configurado corretamente na aba Gestão.")
    
    for mes_str in meses_periodo:
        # Filtra lançamentos do mês específico
        mask_mes = pd.to_datetime(df['data']).dt.strftime('%Y-%m') == mes_str
        df_mes = df[mask_mes].copy()
        
        # Cálculos do mês (baseado no Planejado para projeção)
        entradas_mes = df_mes[df_mes['tipo'] == 'Entrada']['valor_plan'].sum()
        saidas_mes = df_mes[df_mes['tipo'] == 'Saída']['valor_plan'].sum()
        saldo_final_mes = saldo_acumulado_mes + entradas_mes - saidas_mes
        
        nome_mes_exibicao = datetime.strptime(mes_str, '%Y-%m').strftime('%m/%Y')
        
        # Expansor por Mês
        with st.expander(f"📅 {nome_mes_exibicao} | Saldo Final: R$ {format_moeda(saldo_final_mes)}"):
            col1, col2, col3, col4 = st.columns(4)
            
            col1.metric("Saldo Inicial", f"R$ {format_moeda(saldo_acumulado_mes)}")
            col2.metric("Entradas (+)", f"R$ {format_moeda(entradas_mes)}", delta_color="normal")
            col3.metric("Saídas (-)", f"R$ {format_moeda(saidas_mes)}", delta_color="inverse")
            col4.metric("Saldo Final", f"R$ {format_moeda(saldo_final_mes)}")
            
            if not df_mes.empty:
                # Formatação para exibição na tabela
                df_exibir = df_mes.sort_values('data').copy()
                df_exibir['Data'] = pd.to_datetime(df_exibir['data']).dt.strftime('%d/%m/%Y')
                df_exibir['Valor (R$)'] = df_exibir['valor_plan'].apply(format_moeda)
                
                # Seleção de colunas para a tabela
                st.table(df_exibir[['Data', 'descricao', 'tipo', 'Valor (R$)', 'status']])
            else:
                st.write("ℹ️ Nenhum lançamento para este mês.")
        
        # O saldo final deste mês vira o inicial do próximo
        saldo_acumulado_mes = saldo_final_mes

    # Botão para voltar ao topo
    if st.button("Voltar ao Topo", key="btn_topo_lanc"):
        ir_para_o_topo()
        # --- TELA: PROJETAR ---
elif escolha == "📅 Projetar":
    st.markdown(f'<div class="titulo-tela">Projetar Lançamentos: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    if st.session_state.msg_sucesso:
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    # Formulário de Projeção
    with st.container():
        c1, c2 = st.columns([2, 1])
        desc_proj = c1.text_input("Descrição do Lançamento", placeholder="Ex: Aluguel, Venda Cliente X...")
        valor_proj_txt = c2.text_input("Valor (R$)", value="0,00")
        
        tipo_proj = st.selectbox("Tipo de Movimentação", ["Saída", "Entrada"])
        
        with st.expander("Configurar Recorrência e Datas", expanded=True):
            col_a, col_b, col_c = st.columns(3)
            dia_mes = col_a.text_input("Dia do Mês (1-31 ou * para todos)", "")
            dia_semana = col_b.selectbox("Dia da Semana", ["", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"])
            dia_especifico = col_c.date_input("Data Única Especial", value=None)
            
            fds_regra = st.radio("Regra para Fins de Semana", ["Manter Data", "Antecipar para Sexta", "Postergar para Segunda"], horizontal=True)
        
        col_ini, col_fim = st.columns(2)
        data_inicio_proj = col_ini.date_input("Data de Início da Projeção", value=datetime.now().date())
        data_fim_proj = col_fim.date_input("Data Limite da Projeção", value=d_fim_db)

    # Lógica de Inserção
    if st.button("Gerar e Incluir Lançamentos", use_container_width=True):
        valor_num = parse_moeda(valor_proj_txt)
        data_cursor = data_inicio_proj
        lista_para_inserir = []
        
        # Mapeamento de dias para o Python (0=Segunda, 6=Domingo)
        mapa_dias = {"Segunda":0, "Terça":1, "Quarta":2, "Quinta":3, "Sexta":4, "Sábado":5, "Domingo":6}
        
        # CORREÇÃO DEFINITIVA (Anexo image_c66aff): Mantém o acento para o Check Constraint do Banco
        tipo_banco = "Entrada" if tipo_proj == "Entrada" else "Saída"

        #while data_cursor <= data_fim_proj:
        while data_cursor <= data_fim_proj:
            # Verifica se a data atual bate com os filtros
            match_dia_especifico = (dia_especifico is None or data_cursor == dia_especifico)
            match_dia_mes = (dia_mes == "" or dia_mes == "*" or str(data_cursor.day) == dia_mes)
            match_dia_semana = (dia_semana == "" or data_cursor.weekday() == mapa_dias[dia_semana])
            
            if match_dia_especifico and match_dia_mes and match_dia_semana:
                data_final_lanc = data_cursor
                
                # Regra de FDS (Antecipa/Posterga)
                if fds_regra != "Manter Data" and data_final_lanc.weekday() >= 5:
                    if fds_regra == "Posterga para Segunda":
                        dias_adicionar = 2 if data_final_lanc.weekday() == 5 else 1
                        data_final_lanc += timedelta(days=dias_adicionar)
                    elif fds_regra == "Antecipar para Sexta":
                        dias_subtrair = 1 if data_final_lanc.weekday() == 5 else 2
                        data_final_lanc -= timedelta(days=dias_subtrair)
                
                # O CÓDIGO QUE VOCÊ DEVE GARANTIR QUE ESTEJA ASSIM:
                tipo_banco = "Entrada" if tipo_proj == "Entrada" else "Saída"

                lista_para_inserir.append({
                    "projeto_id": st.session_state.projeto_ativo,
                    "usuario_id": uid,
                    "data": data_final_lanc.strftime('%Y-%m-%d'),
                    "data_vencimento": data_final_lanc.strftime('%Y-%m-%d'),
                    "descricao": desc_proj,
                    "valor_plan": valor_num,
                    "valor_real": 0.0,
                    "tipo": tipo_banco,
                    "status": 'Planejado'
                })
            
            data_cursor += timedelta(days=1)
            # Verifica se a data atual bate com os filtros
            #match_dia_especifico = (dia_especifico is None or data_cursor == dia_especifico)
            #match_dia_mes = (dia_mes == "" or dia_mes == "*" or str(data_cursor.day) == dia_mes)
            #match_dia_semana = (dia_semana == "" or data_cursor.weekday() == mapa_dias[dia_semana])
            #
            #if match_dia_especifico and match_dia_mes and match_dia_semana:
            #    data_final_lanc = data_cursor
            #    
            #    # Aplica regra de FDS
            #    if fds_regra != "Manter Data" and data_final_lanc.weekday() >= 5:
            #        if fds_regra == "Posterga para Segunda":
            #            dias_adicionar = 2 if data_final_lanc.weekday() == 5 else 1
            #            data_final_lanc += timedelta(days=dias_adicionar)
            #            dias_subtrair = 1 if data_final_lanc.weekday() == 5 else 2
            #            data_final_lanc -= timedelta(days=dias_subtrair)
            #    
            #    lista_para_inserir.append({
            #        "projeto_id": st.session_state.projeto_ativo,
            #        "usuario_id": uid,
            #        "data": data_final_lanc.strftime('%Y-%m-%d'),
            #        "data_vencimento": data_final_lanc.strftime('%Y-%m-%d'), # Coluna obrigatória
            #        "descricao": desc_proj,
            #        "valor_plan": valor_num,
            #        "valor_real": 0.0,
            #        "tipo": tipo_banco,
            #        "status": 'Planejado'
            #    })
            #
            #data_cursor += timedelta(days=1)

        if lista_para_inserir:
            try:
                supabase.table("lancamentos").insert(lista_para_inserir).execute()
                st.session_state.msg_sucesso = f"✅ Sucesso: {len(lista_para_inserir)} lançamentos gerados!"
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao inserir no banco: {e}")
        else:
            st.warning("Nenhuma data correspondeu aos critérios selecionados.")

# --- TELA: CONCILIAÇÃO ---
elif escolha == "✅ Conciliação":
    st.markdown(f'<div class="titulo-tela">Conciliação: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    # Filtra apenas lançamentos até HOJE que estão como 'Planejado' ou já 'Realizado'
    hoje = datetime.now().date()
    df_conciliar = df[pd.to_datetime(df['data']).dt.date <= hoje].sort_values('data', ascending=False)
    
    if df_conciliar.empty:
        st.info("Nada para conciliar até a data de hoje.")
    else:
        for _, row in df_conciliar.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                dt_format = pd.to_datetime(row['data']).strftime('%d/%m/%Y')
                c1.write(f"**{dt_format}** - {row['descricao']}")
                c2.write(f"Previsto: R$ {format_moeda(row['valor_plan'])}")
                
                if row['status'] == 'Planejado':
                    v_real_input = c3.text_input("Valor Real", key=f"input_{row['id']}", placeholder="0,00")
                    if c4.button("Confirmar", key=f"btn_{row['id']}"):
                        valor_confirmado = parse_moeda(v_real_input) if v_real_input else row['valor_plan']
                        supabase.table("lancamentos").update({
                            "valor_real": valor_confirmado, 
                            "status": 'Realizado'
                        }).eq("id", row['id']).execute()
                        st.rerun()
                else:
                    c3.write(f"Pago: R$ {format_moeda(row['valor_real'])}")
                    c4.write("✅ Conciliado")
            st.divider()
            # --- TELA: GESTÃO ---
elif escolha == "⚙️ Gestão":
    st.markdown('<div class="titulo-tela">Gestão de Projetos e Assinatura</div>', unsafe_allow_html=True)
    
    if st.session_state.msg_sucesso:
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    # Seleção de Fluxo Existente
    lista_opcoes = ["-- Selecionar Fluxo --"] + projs
    fluxo_selecionado = st.selectbox("Trocar para outro Fluxo de Caixa:", lista_opcoes)
    
    if fluxo_selecionado != "-- Selecionar Fluxo --" and fluxo_selecionado != st.session_state.projeto_ativo:
        st.session_state.projeto_ativo = fluxo_selecionado
        st.rerun()

    st.divider()
    
    # Configurações do Fluxo Atual ou Novo
    st.subheader("Configurações do Fluxo")
    nome_fluxo_input = st.text_input("Nome do Fluxo (Ex: Pessoal, Empresa X)", 
                                    value=st.session_state.projeto_ativo if st.session_state.projeto_ativo else "")
    
    col_g1, col_g2 = st.columns(2)
    data_ini_gestao = col_g1.date_input("Data de Início do Fluxo", value=d_ini_db)
    data_fim_gestao = col_g2.date_input("Data de Término do Fluxo", value=d_fim_db)
    
    # Opção de WhatsApp
    ativar_zap = st.checkbox("Ativar Notificações via WhatsApp (+ R$ 10,00/mês)", 
                             value=(st.session_state.zap_ativo == 1))
    
    # Cálculo de Valor (Regra de Negócio do Security)
    valor_mensalidade = security.calcular_valor_v01(len(projs), 
                                                   data_ini_gestao.strftime('%Y-%m-%d'), 
                                                   data_fim_gestao.strftime('%Y-%m-%d'))
    
    if ativar_zap:
        valor_mensalidade += 10.0
        
    st.info(f"💳 Valor Estimado da Assinatura: **R$ {format_moeda(valor_mensalidade)} / mês**")
    
    col_btn1, col_btn2 = st.columns([1, 1])
    
    if col_btn1.button("Salvar Alterações / Criar Fluxo", use_container_width=True):
        if nome_fluxo_input:
            # Prepara dados para Upsert
            dados_projeto = {
                "projeto_id": nome_fluxo_input,
                "usuario_id": uid,
                "saldo_inicial": s_db,
                "data_ini": data_ini_gestao.strftime('%Y-%m-%d'),
                "data_fim": data_fim_gestao.strftime('%Y-%m-%d')
            }
            
            # Verifica se já existe para pegar o ID e não duplicar (Anexo c581c7)
            check_pj = supabase.table("config_projetos").select("id").eq("projeto_id", nome_fluxo_input).eq("usuario_id", uid).execute()
            if check_pj.data:
                dados_projeto["id"] = check_pj.data[0]["id"]
            
            # Salva Configurações do Projeto
            supabase.table("config_projetos").upsert(dados_projeto).execute()
            
            # Atualiza status do WhatsApp no cadastro do usuário
            supabase.table("usuarios").update({"zap_ativo": 1 if ativar_zap else 0}).eq("id", uid).execute()
            st.session_state.zap_ativo = 1 if ativar_zap else 0
            
            st.session_state.projeto_ativo = nome_fluxo_input
            st.session_state.msg_sucesso = "✅ Configurações salvas com sucesso!"
            st.rerun()
        else:
            st.error("Por favor, insira um nome para o fluxo.")

    # Opção de Exclusão (Perigosa)
    if st.session_state.projeto_ativo:
        with st.expander("⚠️ Zona de Perigo"):
            st.warning(f"Isso excluirá permanentemente o fluxo '{st.session_state.projeto_ativo}' e todos os seus lançamentos.")
            confirmar_exclusao = st.checkbox("Eu entendo que os dados serão perdidos.")
            if st.button("EXCLUIR FLUXO ATUAL", type="primary") and confirmar_exclusao:
                # Deleta lançamentos e configurações
                supabase.table("lancamentos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).execute()
                supabase.table("config_projetos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid).execute()
                
                st.session_state.projeto_ativo = None
                st.rerun()

# --- RODAPÉ ---
st.divider()
st.caption("ORCAS v0.1 - Sistema de Gestão de Fluxo de Caixa Projetado")