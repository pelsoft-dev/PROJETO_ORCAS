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
st.set_page_config(page_title="ORCAS - Gestão Financeira", page_icon="🐋", layout="wide", initial_sidebar_state="expanded")

def ir_para_o_topo():
    components.html("""<script>window.parent.document.getElementById('topo-ancora').scrollIntoView();</script>""", height=0)

st.markdown("""
    <style>
    /* 1. Esconde o menu de 3 linhas e o rodapé */
    #MainMenu {visibility: hidden;} 
    footer {visibility: hidden;}
    
    /* 2. Deixa o cabeçalho transparente para manter o botão ">>" visível */
    [data-testid="stHeader"] {
        background: rgba(0,0,0,0) !important;
        color: #1E3A8A !important;
    }

    /* 3. Esconde especificamente a coroa, o botão de Deploy e o status */
    .stAppDeployButton {display: none !important;}
    [data-testid="stStatusWidget"] {display: none !important;}
    #stDecoration {display: none !important;}
    [data-testid="stToolbar"] {display: none !important;}

    /* 4. Mantém seus formatos e estilos originais rigorosamente */
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
            
            col_btn_l1, col_btn_l2 = st.columns(2)
            if col_btn_l1.button("Entrar no Sistema"):
                senha_hash = hashlib.sha256(str.encode(se)).hexdigest()
                res = supabase.table("usuarios").select("id, vencimento, zap_ativo").eq("email", em).eq("senha", senha_hash).execute()
                if res.data: 
                    user_data = res.data[0]
                    st.session_state.logado = True
                    # CHAVE MESTRA: Blindada contra cálculos de data
                    st.session_state.CHAVE_MESTRA_UUID = str(user_data['id'])
                    st.session_state.usuario = em
                    st.session_state.vencimento = str(user_data['vencimento'])
                    st.session_state.zap_ativo = user_data.get('zap_ativo', 0)
                    st.session_state.projeto_ativo = None
                    st.rerun()
                else:
                    st.error("E-mail ou senha incorretos.")
            
            if col_btn_l2.button("Esqueci minha Senha"):
                st.info("Por favor, entre em contato com o suporte administrativo do ORCAS.")

        with aba[1]:
            st.info("Para criar uma nova conta, entre em contato com o suporte administrativo do ORCAS.")
    st.stop()

# --- 4. ESTADO E DADOS ---
# Aqui definimos a variável que será usada em todo o script
ID_USUARIO_LOGADO = str(st.session_state.get('CHAVE_MESTRA_UUID', ''))
vencimento_str = st.session_state.get('vencimento', '2026-01-01')
venc_dt_objeto = datetime.strptime(vencimento_str, '%Y-%m-%d').date()

# SEGURANÇA: Passamos o ID e o cálculo de dias sem criar variáveis 'uid' perigosas
if ID_USUARIO_LOGADO:
    security.verificar_bloqueio_v01(ID_USUARIO_LOGADO, (venc_dt_objeto - datetime.now().date()).days)

# Busca de projetos usando o ID correto
projs_req = supabase.table("config_projetos").select("projeto_id").eq("usuario_id", ID_USUARIO_LOGADO).execute()
projs = [r['projeto_id'] for r in projs_req.data]

if 'projeto_ativo' not in st.session_state:
    st.session_state.projeto_ativo = None
if 'msg_sucesso' not in st.session_state:
    st.session_state.msg_sucesso = None
if 'confirmar_exclusao_ativa' not in st.session_state:
    st.session_state.confirmar_exclusao_ativa = False

s_db = 0.0
d_ini_db = None 
d_fim_db = None 

if st.session_state.projeto_ativo:
    cfg_req = supabase.table("config_projetos").select("*").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", ID_USUARIO_LOGADO).execute()
    if cfg_req.data:
        cfg = cfg_req.data[0]
        s_db = cfg.get('saldo_inicial', 0.0)
        d_ini_db = datetime.strptime(cfg['data_ini'], '%Y-%m-%d').date()
        d_fim_db = datetime.strptime(cfg['data_fim'], '%Y-%m-%d').date()

# --- 5. BARRA LATERAL ---
with st.sidebar:
    st.markdown('<div class="logo-sidebar">🐋 ORCAS</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="user-email">👤 {st.session_state.usuario}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="venc-text">📅 EXPIRA EM: {venc_dt_objeto.strftime("%d/%m/%Y")}</div>', unsafe_allow_html=True)

    if st.session_state.projeto_ativo:
        st.markdown(f'<div class="project-tag-sidebar">Plano Ativo: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
        # REMOVIDO: Bloco de Saldo Inicial conforme solicitado

    st.divider()
    menu_opcoes = ["🏠 Dashboard", "📑 Lançamentos", "📅 Projetar", "✅ Conciliação", "⚙️ Gestão", "📊 Admin"]
    
    # ACERTO CRÍTICO: Inicialização e Sincronização da Navegação
    # Se a variável 'escolha' não existe no state ou não está na lista, definimos o padrão
    if 'escolha' not in st.session_state or st.session_state.escolha not in menu_opcoes:
        st.session_state.escolha = "⚙️ Gestão" if st.session_state.projeto_ativo is None else "🏠 Dashboard"
    
    # Busca o índice da escolha atual para o rádio respeitar o estado
    idx_atual = menu_opcoes.index(st.session_state.escolha)
    
    # O rádio agora lê o index dinamicamente do session_state
    escolha_radio = st.radio("Navegação", menu_opcoes, index=idx_atual, key="navegacao_principal", label_visibility="collapsed")
    
    # Atualiza a variável global que controla as telas (if/elif)
    st.session_state.escolha = escolha_radio
    escolha = st.session_state.escolha

    st.divider()
    if st.button("Sair do Sistema"):
        st.session_state.clear()
        st.rerun()

st.markdown("<div id='topo-ancora'></div>", unsafe_allow_html=True)

# Redirecionamento de segurança se não houver plano ativo
if st.session_state.projeto_ativo is None and escolha not in ["⚙️ Gestão", "📊 Admin"]:
    st.session_state.escolha = "⚙️ Gestão"
    st.rerun()
# --- 6. CARREGAMENTO DO DATAFRAME (CORRIGIDO) ---
# Substituímos o 'uid' que não existe mais por 'ID_USUARIO_LOGADO'
res_l = supabase.table("lancamentos").select("*").eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", ID_USUARIO_LOGADO).order("data").execute()
df = pd.DataFrame(res_l.data)

if not df.empty:
    df.columns = [c.lower() for c in df.columns]
else:
    df = pd.DataFrame(columns=[
        'id', 'data', 'descricao', 'tipo', 'valor_plan', 'valor_real', 
        'status', 'permite_parcial', 'projeto_id', 'usuario_id', 
        'data_vencimento', 'id_pai', 'usar_media', 'complemento_texto',
        'correcao_freq', 'correcao_valor'
    ])

# --- TELA: GESTÃO (REGRAS DE DATAS E SALDO) ---
# --- TELA: GESTÃO (TOPO DA CADEIA DE IF/ELIF) ---
if escolha == "⚙️ Gestão":
    st.markdown('<div class="titulo-tela">Gestão de Planos e Assinaturas</div>', unsafe_allow_html=True)
    
    hoje = datetime.now().date()
    uid_gestao = st.session_state.get('CHAVE_MESTRA_UUID')

    if st.session_state.get('msg_sucesso'):
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    col_l1_1, col_l1_2 = st.columns(2)
    lista_gestao = [""] + projs
    
    # ACERTO: Captura a seleção
    plano_sel = col_l1_1.selectbox("Selecione um Plano já existente:", lista_gestao)
    
    # ACERTO CRÍTICO E DEFINITIVO: 
    # Se o plano mudou, forçamos a variável de navegação no STATE e damos rerun.
    # IMPORTANTE: No seu código da SIDEBAR, o seu menu DEVE usar st.session_state.escolha como index.
    if plano_sel != "" and plano_sel != st.session_state.get('projeto_ativo'):
        st.session_state.projeto_ativo = plano_sel
        st.session_state.escolha = "⚙️ Gestão" 
        st.rerun()

    # ACERTO: O valor do input só existe se houver projeto_ativo, caso contrário fica vazio ""
    # Isso evita que o valor de um plano anterior fique "preso" na tela ao trocar
    nome_plano_input = col_l1_2.text_input("Nome do Plano carregado ou Nome para criação de um novo Plano", value=st.session_state.projeto_ativo if st.session_state.projeto_ativo else "")

    # ACERTO: O bloco de cálculos e exibição SÓ EXISTE se houver um nome de plano.
    # Se não houver, o "Valor da Assinatura" não é sequer processado (ZERA O ERRO).
    if nome_plano_input and nome_plano_input.strip() != "":
        col_l2_1, col_l2_2 = st.columns(2)
        
        # MANTIDO RIGOROSAMENTE O FORMATO DD/MM/AAAA
        d_ini_g = col_l2_1.date_input("Data de Início:", value=d_ini_db if d_ini_db else hoje, format="DD/MM/YYYY")
        d_fim_g = col_l2_2.date_input("Data de Término:", value=d_fim_db if d_fim_db else hoje + timedelta(days=730), format="DD/MM/YYYY")

        col_l3_1, col_l3_2 = st.columns(2)
        valor_saldo_exibir = format_moeda(s_db) if s_db is not None else "0,00"
        saldo_input = col_l3_1.text_input("Saldo Inicial:", value=valor_saldo_exibir)
        
        meses_total = (d_fim_g.year - d_ini_g.year) * 12 + (d_fim_g.month - d_ini_g.month)
        col_l3_2.text_input("Período do Plano: (Veja abaixo)", value=f"{meses_total} meses", disabled=True)

        col_l4_1, col_l4_2 = st.columns(2)
        ativar_zap = col_l4_1.checkbox("Adicionar o Resumo diário via WHATSAPP", value=(st.session_state.get('zap_ativo', 0) == 1))
        
        # ACERTO: Cálculo isolado dentro da condição de plano ativo
        v_estimado = security.calcular_valor_v01(len(projs), d_ini_g.strftime('%Y-%m-%d'), d_fim_g.strftime('%Y-%m-%d'))
        if ativar_zap: v_estimado += 9.85
        
        col_l4_2.markdown(f'<div style="background-color: #87CEFA; padding: 10px; text-align: center; border-radius: 5px; font-weight: bold; color: black;">Valor da Assinatura Mensal: R$ {format_moeda(v_estimado)}</div>', unsafe_allow_html=True)

        st.divider()

        btn_col1, btn_col2 = st.columns(2)
        
        if btn_col1.button("Salvar alterações ou Criar o novo Plano", use_container_width=True):
            dados_p = {
                "projeto_id": nome_plano_input, 
                "usuario_id": uid_gestao, 
                "saldo_inicial": parse_moeda(saldo_input),
                "data_ini": d_ini_g.strftime('%Y-%m-%d'), 
                "data_fim": d_fim_g.strftime('%Y-%m-%d')
            }
            res_p = supabase.table("config_projetos").select("id").eq("projeto_id", nome_plano_input).eq("usuario_id", uid_gestao).execute()
            if res_p.data: dados_p["id"] = res_p.data[0]["id"]
            
            supabase.table("config_projetos").upsert(dados_p).execute()
            supabase.table("usuarios").update({"zap_ativo": 1 if ativar_zap else 0}).eq("id", uid_gestao).execute()
            
            st.session_state.projeto_ativo = nome_plano_input
            st.session_state.msg_sucesso = "Plano e Saldo Inicial salvos com sucesso!"
            # ACERTO: Força permanência na tela de Gestão
            st.session_state.escolha = "⚙️ Gestão"
            st.rerun()

        if st.session_state.projeto_ativo:
            if btn_col2.button("Excluir Plano", type="primary", use_container_width=True):
                st.session_state.confirmar_exclusao_plano = True

        if st.session_state.get('confirmar_exclusao_plano', False):
            st.error(f"Deseja mesmo excluir o plano {st.session_state.projeto_ativo}?")
            ce1, ce2 = st.columns(2)
            if ce1.button("CONFIRMAR EXCLUSÃO"):
                supabase.table("lancamentos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid_gestao).execute()
                supabase.table("config_projetos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid_gestao).execute()
                st.session_state.projeto_ativo = None
                st.session_state.confirmar_exclusao_plano = False
                st.session_state.escolha = "⚙️ Gestão"
                st.rerun()
            if ce2.button("CANCELAR"):
                st.session_state.confirmar_exclusao_plano = False
                st.rerun()
    else:
        # Mensagem informativa: O valor da assinatura FICA ZERADO (não aparece) até escolher o plano
        st.info("Por favor, selecione um plano existente ou digite um nome para iniciar a configuração.")

    st.markdown("""
    <div style="font-size: 12px; color: #333; margin-top: 20px; text-align: justify; line-height: 1.6;">
    Sua Assinatura ORCAS BABY mensal custa R$ 19,90 e contempla 2 Planos de 24 meses cada um, mas se você quiser ou necessitar, é possível aumentar o período de um Plano em blocos adicionais de 12 meses tendo um acréscimo de R$ 6,80 para cada 12 meses adicionais.<br>
    Para aumentar o número de Planos (Padrão - 24 meses), o valor é de R$ 12,00 por Plano adicional.<br>
    Para receber um Resumo Diário das análises e pendências, o que preciso pagar e receber hoje, quanto já gastei de supermercado até hoje, quanto já gastei nessa reforma, etc de seu Plano via Whatsapp terá um acréscimo de R$ 9,85 por Plano.
    </div>
    """, unsafe_allow_html=True)

# --- TELA: DASHBOARD ---
elif escolha == "🏠 Dashboard":
    st.markdown(f'<div class="titulo-tela">Dashboard: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    if not df.empty and 'data' in df.columns:
        df['dt'] = pd.to_datetime(df['data'])
        
        # AJUSTE: Soma valor_real e parcial_real. Como o pai tem parcial_real=0 
        # e os filhos têm valor_real=0, a soma simples evita duplicidade e pega tudo > 0.
        df['v_real_full'] = df['valor_real'] + df['parcial_real']
        
        df['v'] = df.apply(
            lambda x: (x['v_real_full'] if (x['status'] == 'Realizado' or x['v_real_full'] > 0) else x['valor_plan']) * (1 if x['tipo'] == 'Entrada' else -1), 
            axis=1
        )
        
        df_diario = df.groupby('dt')['v'].sum().reset_index()
        df_diario = df_diario.sort_values('dt')
        df_diario['Saldo Acumulado'] = df_diario['v'].cumsum() + s_db
        
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
        
        st.subheader("Análise Mensal: Planejado x Realizado")
        df['MesAno'] = df['dt'].dt.strftime('%b/%y')
        
        # AGREGAÇÃO: Soma o planejado e a nova coluna que consolida qualquer valor realizado > 0
        res_mensal = df.groupby(['MesAno', 'tipo']).agg({'valor_plan':'sum', 'v_real_full':'sum'}).reset_index()
        res_mensal.rename(columns={'v_real_full': 'valor_real'}, inplace=True)
        
        meses_ordem = df.sort_values('dt')['MesAno'].unique()
        
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

# --- TELA: LANÇAMENTOS ---
# --- TELA: LANÇAMENTOS ---
elif escolha == "📑 Lançamentos":
    st.markdown(f'<div class="titulo-tela">Lançamentos: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    if d_ini_db and d_fim_db:
        # Loop de meses e saldo acumulado original (83+ linhas mantidas)
        meses_periodo = []
        data_atual_loop = d_ini_db.replace(day=1)
        while data_atual_loop <= d_fim_db:
            meses_periodo.append(data_atual_loop.strftime('%Y-%m'))
            if data_atual_loop.month == 12: 
                data_atual_loop = data_atual_loop.replace(year=data_atual_loop.year + 1, month=1)
            else: 
                data_atual_loop = data_atual_loop.replace(month=data_atual_loop.month + 1)
        
        saldo_acumulado_mes = s_db
        
        for mes_str in meses_periodo:
            mask_mes = pd.to_datetime(df['data']).dt.strftime('%Y-%m') == mes_str
            df_mes = df[mask_mes].copy()
            
            # ACERTO CABEÇALHO: Lógica de soma condicional para Entradas e Saídas
            def calcular_total_tipo(df_tipo):
                total = 0
                # ACERTO: Considera itens planejados OU itens diretos (plan=0 e real>0)
                itens_principais = df_tipo[(df_tipo['valor_plan'] > 0) | ((df_tipo['valor_plan'] == 0) & (df_tipo['valor_real'] > 0))]
                
                for _, x in itens_principais.iterrows():
                    if x['permite_parcial']:
                        # Mantém a lógica: maior entre planejado e soma das parciais
                        v_parciais = df_mes[(df_mes['descricao'] == x['descricao']) & (df_mes['valor_plan'] == 0)]['parcial_real'].sum()
                        total += max(x['valor_plan'], v_parciais)
                    else:
                        # ACERTO: Se valor realizado > 0, usa ele, senão usa o planejado
                        total += x['valor_real'] if x['valor_real'] > 0 else x['valor_plan']
                return total

            entradas_mes = calcular_total_tipo(df_mes[df_mes['tipo'] == 'Entrada'])
            saidas_mes = calcular_total_tipo(df_mes[df_mes['tipo'] == 'Saída'])
                
            saldo_final_mes = saldo_acumulado_mes + entradas_mes - saidas_mes
            nome_mes_exibicao = datetime.strptime(mes_str, '%Y-%m').strftime('%m/%Y')
            
            with st.expander(f"📅 {nome_mes_exibicao} | Saldo Final: R$ {format_moeda(saldo_final_mes)}"):
                # Métricas do topo (originais)
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Saldo Inicial", f"R$ {format_moeda(saldo_acumulado_mes)}")
                col2.metric("Entradas (+)", f"R$ {format_moeda(entradas_mes)}")
                col3.metric("Saídas (-)", f"R$ {format_moeda(saidas_mes)}")
                col4.metric("Saldo Final", f"R$ {format_moeda(saldo_final_mes)}")
                st.divider()

                if not df_mes.empty:
                    # Cabeçalho da Lista
                    h1, h2, h3, h4, h5, h6 = st.columns([1.2, 3, 0.5, 1.2, 1.2, 0.8])
                    h1.write("**Data**"); h2.write("**Descrição**"); h3.write("**E/S**")
                    h4.write("**V. Plan**"); h5.write("**V. Real**"); h6.write("**Status**")

                    # ACERTO: Itens Pais ou Diretos (valor_plan > 0 OU (plan=0 e real>0))
                    df_exibir = df_mes[(df_mes['valor_plan'] > 0) | ((df_mes['valor_plan'] == 0) & (df_mes['valor_real'] > 0))].sort_values('data')
                    
                    for _, row in df_exibir.iterrows():
                        c1, c2, c3, c4, c5, c6 = st.columns([1.2, 3, 0.5, 1.2, 1.2, 0.8])
                        c1.write(pd.to_datetime(row['data']).strftime('%d/%m/%Y'))
                        c2.write(row['descricao'])
                        c3.write(row['tipo'][0])
                        c4.write(format_moeda(row['valor_plan']))
                        
                        v_acum = df_mes[df_mes['descricao'] == row['descricao']]['parcial_real'].sum()
                        c5.write(format_moeda(v_acum if v_acum > 0 else row['valor_real']))
                        c6.write('PLAN' if row['status'] == 'Planejado' else 'REAL')

                        # ASSOCIAÇÃO POR TEXTO (Filhos: valor_plan == 0 e parcial_real > 0)
                        filhos = df_mes[(df_mes['descricao'] == row['descricao']) & (df_mes['valor_plan'] == 0) & (df_mes['parcial_real'] > 0)]
                        for _, filho in filhos.iterrows():
                            f1, f2, f3, f4, f5, f6 = st.columns([1.2, 3, 0.5, 1.2, 1.2, 0.8])
                            # ACERTO: Retorno do formato DD/MM/AAAA (4 dígitos no ano)
                            f2.markdown(f"<span style='color:gray; padding-left:20px;'> >>> {pd.to_datetime(filho['parcial_data']).strftime('%d/%m/%Y')}</span>", unsafe_allow_html=True)
                            f3.markdown(f"<span style='color:gray;'>{filho['tipo'][0]}</span>", unsafe_allow_html=True)
                            f5.markdown(f"<span style='color:gray;'>{format_moeda(filho['parcial_real'])}</span>", unsafe_allow_html=True)
                            f6.markdown(f"<span style='color:gray;'>REAL</span>", unsafe_allow_html=True)
                else:
                    st.write("ℹ️ Nenhum lançamento para este mês.")
            saldo_acumulado_mes = saldo_final_mes

    if st.button("Voltar ao Topo", key="btn_topo_lanc"): 
        ir_para_o_topo()

# --- TELA: PROJETAR ---
elif escolha == "📅 Projetar":
    st.markdown(f'<div class="titulo-tela">Projetar: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    # Mantém a exibição da mensagem de sucesso no topo
    if st.session_state.msg_sucesso: 
        st.success(st.session_state.msg_sucesso)
        st.session_state.msg_sucesso = None

    col_d1, col_d2 = st.columns([4, 2])
    desc = col_d1.text_input("Descrição", key="pj_d")
    comp_txt = col_d2.text_input("Complemento", help="Será adicionado ao final da descrição")
    
    col_v, col_t = st.columns(2)
    v_t = col_v.text_input("Valor", "0,00")
    tipo = col_t.selectbox("Tipo", ["Saída", "Entrada"])

    with st.expander("Recorrência e Datas"):
        c1, c2, c3 = st.columns(3)
        d_m = c1.text_input("Dia (1-31, DD/MM ou *)", "")
        d_s = c2.selectbox("Dia da Semana", ["", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"])
        d_e = c3.date_input("Dia Específico", value=None, format="DD/MM/YYYY")
        
        n_ocorrencias = st.number_input("Nº de Ocorrências (0 = usar Data Até)", min_value=0, step=1)
        fds = st.radio("Se cair em Fim de Semana:", ["Manter", "Antecipa", "Posterga"], horizontal=True)
        
        c_i, c_f = st.columns(2)
        i_p = c_i.date_input("Início", value=datetime.now().date(), format="DD/MM/YYYY", key="pj_data_ini")
        f_p = c_f.date_input("Até", value=d_fim_db if d_fim_db else datetime.now().date(), format="DD/MM/YYYY", key="pj_data_fim")

    with st.expander("🛠️ Projeção Avançada", expanded=False):
        st.markdown("**Regras de Correção Automática**")
        col_c1, col_c2, col_c3 = st.columns([2, 2, 3])
        usar_corrc = col_c1.checkbox("Corrigir este valor?")
        c_quando = col_c2.selectbox("Quando:", ["Todo mês", "Todo ano"])
        c_base = col_c3.selectbox("Com base em:", ["Média dos Realizados", "Percentual Fixo (%)", "IGPM"])
        c_val_fixo = st.text_input("Valor do Percentual (se fixo)", "0,00")

        st.divider()

        st.markdown("**Realizações Parciais e Resíduos**")
        col_p1, col_p2, col_p3 = st.columns([2, 2, 3])
        permitir_parcial = col_p1.checkbox("Permitir parciais?")
        p_ate = col_p2.selectbox("Até:", ["Último dia do mês", "Último dia do ano", "Sempre"])
        p_depois = col_p3.selectbox("Depois disso:", [
            "Zera o Realizado", 
            "Adiciona a diferença no próximo Planejado",
            "Copia Planejado atualizado para o próximo"
        ])

    btn_col1, btn_col2, _ = st.columns([1, 1, 2])

    if btn_col1.button("Incluir", use_container_width=True):
        # Definição local de uid para garantir funcionamento do Incluir
        uid_local = st.session_state.get('CHAVE_MESTRA_UUID')
        v = parse_moeda(v_t)
        v_pct = parse_moeda(c_val_fixo) / 100
        curr = i_p
        lista_bulk = [] 
        gerados = 0
        d_map = {"Segunda":0,"Terça":1,"Quarta":2,"Quinta":3,"Sexta":4,"Sábado":5,"Domingo":6}
        
        limite_loop = f_p if n_ocorrencias == 0 else i_p + timedelta(days=3650)

        while curr <= limite_loop:
            match_dm = False
            if "/" in d_m:
                try:
                    dia_a, mes_a = map(int, d_m.split("/"))
                    if curr.day == dia_a and curr.month == mes_a: match_dm = True
                except: pass
            else:
                match_dm = (d_m == "" or d_m == "*" or str(curr.day) == d_m)

            if (d_e is None or curr == d_e) and match_dm and (d_s == "" or curr.weekday() == d_map[d_s]):
                dt_f = curr
                if permitir_parcial:
                    dt_f = dt_f.replace(day=1)
                elif fds != "Manter" and dt_f.weekday() >= 5: 
                    dt_f += timedelta(days=(2 if dt_f.weekday()==5 else 1) if fds=="Posterga" else -1)
                
                nome_final = f"{desc} {comp_txt}".strip() if comp_txt else desc
                lista_bulk.append({
                    "projeto_id": st.session_state.projeto_ativo, 
                    "usuario_id": uid_local, 
                    "data": dt_f.strftime('%Y-%m-%d'), 
                    "data_vencimento": dt_f.strftime('%Y-%m-%d'),
                    "descricao": nome_final, 
                    "valor_plan": v, 
                    "valor_real": 0.0, 
                    "tipo": tipo, 
                    "status": 'Planejado',
                    "permite_parcial": permitir_parcial,
                    "usar_media": (usar_corrc and c_base == "Média dos Realizados"),
                    "complemento_texto": comp_txt if comp_txt else None,
                    "correcao_freq": c_quando if usar_corrc else None,
                    "correcao_valor": v_pct if c_base == "Percentual Fixo (%)" else 0.0
                })
                gerados += 1
                if usar_corrc and c_quando == "Todo mês" and c_base == "Percentual Fixo (%)": v *= (1 + v_pct)

            if n_ocorrencias > 0 and gerados >= n_ocorrencias: break
            curr += timedelta(days=1)
        
        if lista_bulk:
            supabase.table("lancamentos").insert(lista_bulk).execute()
            st.session_state.msg_sucesso = f"Sucesso! {len(lista_bulk)} lançamentos gerados."
            st.rerun()

    # --- CORREÇÃO DO BOTÃO EXCLUIR (uid definido e mensagens restauradas) ---
    if btn_col2.button("Excluir", use_container_width=True):
        if not desc: 
            st.error("Informe a descrição para excluir os lançamentos correspondentes.")
        else:
            st.session_state.confirmar_exclusao_ativa = True

    if st.session_state.get('confirmar_exclusao_ativa', False):
        nome_busca = f"{desc} {comp_txt}".strip() if comp_txt else desc
        uid_exec = st.session_state.get('CHAVE_MESTRA_UUID') # Correção do NameError: uid
        
        if d_e:
            msg_confirma = f"VOCÊ DESEJA EXCLUIR O LANÇAMENTO {nome_busca} DO DIA {d_e.strftime('%d/%m/%Y')}. SIM/NÃO?"
        else:
            msg_confirma = f"VOCÊ DESEJA EXCLUIR TODOS OS LANÇAMENTOS DE {nome_busca} DO PERÍODO DE {i_p.strftime('%d/%m/%Y')} A {f_p.strftime('%d/%m/%Y')}. SIM/NÃO?"
        
        st.warning(msg_confirma)
        exc_c1, exc_c2 = st.columns(2)
        
        if exc_c1.button("SIM", key="btn_confirm_exc_sim"):
            query = supabase.table("lancamentos").delete().eq("projeto_id", st.session_state.projeto_ativo).eq("usuario_id", uid_exec).eq("descricao", nome_busca)
            
            if d_e:
                res_exc = query.eq("data", d_e.strftime('%Y-%m-%d')).execute()
            else:
                res_exc = query.gte("data", i_p.strftime('%Y-%m-%d')).lte("data", f_p.strftime('%Y-%m-%d')).execute()
            
            num_excluidos = len(res_exc.data) if res_exc.data else 0
            # A mensagem agora será exibida no topo após o rerun
            st.session_state.msg_sucesso = f"Sucesso! {num_excluidos} lançamentos excluídos com sucesso."
            st.session_state.confirmar_exclusao_ativa = False
            st.rerun()
            
        if exc_c2.button("NÃO", key="btn_confirm_exc_nao"):
            st.session_state.confirmar_exclusao_ativa = False
            st.rerun()
# --- TELA: CONCILIAÇÃO ---
# --- TELA: CONCILIAÇÃO ---
elif escolha == "✅ Conciliação":
    st.markdown(f'<div class="titulo-tela">Conciliação: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    hoje_c = datetime.now().date()
    ini_mes_c = hoje_c.replace(day=1)
    limite_c = hoje_c - timedelta(days=3)

    # ACERTO: Toggle alinhado à direita
    col_tit, col_tog = st.columns([5, 2])
    abrir_sem_plan = col_tog.toggle("Lançar sem Planejamento", value=st.session_state.get('abrir_sem_plan', False))
    st.session_state.abrir_sem_plan = abrir_sem_plan
    
    st.divider()

    # ACERTO: (2) Alinhamento Horizontal Total dos 3 campos com o botão Confirmar
    if st.session_state.abrir_sem_plan:
        cols_sp = st.columns([2.5, 1, 1.2, 1])
        sp_desc = cols_sp[0].text_input("Descrição", key="sp_desc", placeholder="Ex: Gasto Extra")
        sp_tipo = cols_sp[1].selectbox("E/S", ["Entrada", "Saída"], key="sp_tipo")
        sp_valor = cols_sp[2].text_input("Valor Real", key="sp_valor", value="0,00")
        
        # Alinhamento vertical preciso do botão com os inputs
        with cols_sp[3]:
            st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
            btn_confirmar = st.button("Confirmar", key="btn_sp_conf", use_container_width=True)
        
        if btn_confirmar:
            v_sp = parse_moeda(sp_valor)
            if sp_desc and v_sp > 0:
                # ACERTO: (1) Valor planejado volta a ser 0. 
                # A lógica de exibição agora aceita (valor_plan == 0 e valor_real > 0)
                supabase.table("lancamentos").insert({
                    "projeto_id": str(st.session_state.projeto_ativo),
                    "usuario_id": str(st.session_state.get('CHAVE_MESTRA_UUID')),
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
    df_c['dt_obj'] = pd.to_datetime(df_c['data']).dt.date
    
    # ACERTO NA LÓGICA DE FILTRO: 
    # Agora inclui itens onde valor_plan é 0 mas valor_real é maior que 0 (Lançamentos Diretos)
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

    # Cabeçalho Compacto
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
            
            if c6.button("Confirmar", key=f"btn_p_{row['id']}"):
                v_dig = parse_moeda(v_parc_in)
                if v_dig > 0:
                    supabase.table("lancamentos").insert({
                        "projeto_id": str(st.session_state.projeto_ativo),
                        "usuario_id": str(st.session_state.get('CHAVE_MESTRA_UUID')), 
                        "descricao": row['descricao'], 
                        "data": ini_mes_c.strftime('%Y-%m-%d'), 
                        "data_vencimento": ini_mes_c.strftime('%Y-%m-%d'), 
                        "tipo": row['tipo'],
                        "valor_plan": 0,
                        "valor_real": 0,
                        "status": "Realizado",
                        "parcial_real": v_dig,
                        "parcial_data": hoje_c.strftime('%Y-%m-%d'),
                        "permite_parcial": False
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
                if c6.button("Confirmar", key=f"btn_n_{row['id']}"):
                    v_para_gravar = parse_moeda(v_norm_in)
                    if v_para_gravar == 0:
                        v_para_gravar = row['valor_plan']
                        
                    supabase.table("lancamentos").update({
                        "valor_real": v_para_gravar, 
                        "status": "Realizado"
                    }).eq("id", row['id']).execute()
                    st.rerun()
        st.divider()

# --- TELA: ADMIN (LAYOUT EXCEL / SOLICITAÇÃO 4) ---
# --- TELA: ADMIN ---
elif escolha == "📊 Admin":
    st.markdown(f'<div class="titulo-tela">Administração: {st.session_state.projeto_ativo}</div>', unsafe_allow_html=True)
    
    # Criamos uma cópia para o editor
    df_admin = df.copy()

    # ACERTO (5): Converte a coluna 'data' para string para evitar erro de Arrow/DataEditor
    if 'data' in df_admin.columns:
        df_admin['data'] = df_admin['data'].astype(str)

    st.warning("Cuidado: Alterações aqui impactam diretamente o banco de dados.")

    # Exibe o editor de dados com as configurações originais
    df_editado = st.data_editor(
        df_admin, 
        num_rows="dynamic", 
        key="editor_admin_v1",
        use_container_width=True
    )
    
    if st.button("Salvar Alterações no Banco"):
        # Lógica de salvamento original (iterando pelas linhas editadas)
        try:
            for i, row in df_editado.iterrows():
                # Busca o ID original para atualizar
                id_orig = row['id']
                
                # Monta o dicionário de atualização com base nas colunas existentes
                dados_update = {
                    "descricao": row['descricao'],
                    "valor_plan": row['valor_plan'],
                    "valor_real": row['valor_real'],
                    "tipo": row['tipo'],
                    "status": row['status'],
                    "data": str(row['data']) # Garante que volte como string formatada para o banco
                }
                
                # Executa o update no Supabase
                supabase.table("lancamentos").update(dados_update).eq("id", id_orig).execute()
            
            st.success("Todas as alterações foram salvas com sucesso!")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

    st.divider()
    
    # Botão para limpar mensagens ou estados (conforme sua lógica original)
    if st.button("Limpar Cache do Sistema"):
        st.cache_data.clear()
        st.success("Cache limpo!")
        st.rerun()

    if st.button("Voltar ao Topo", key="btn_topo_admin"): 
        ir_para_o_topo()

# --- RODAPÉ ---
st.divider()
st.caption(f"ORCAS v01 | Usuário: {st.session_state.usuario} | Projeto: {st.session_state.projeto_ativo}")