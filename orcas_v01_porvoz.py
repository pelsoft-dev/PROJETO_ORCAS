from datetime import date, datetime
import json
import re
import time
import unicodedata
from groq import Groq
import streamlit as st

# Limites mensais de uso do recurso por voz
LIMITES_USO = {
    'PADRAO': 30,
    'INTERMEDIARIO': 100,
    'ILIMITADO': 999999,
}


def normalizar_texto(texto):
    """Remove acentos, pontos, traços e converte para maiúsculo para comparação precisa."""
    if not texto:
        return ''
    nfkd = unicodedata.normalize('NFKD', str(texto))
    texto_sem_acento = ''.join([c for c in nfkd if not unicodedata.combining(c)])
    texto_limpo = re.sub(r'[^a-zA-Z0-9\s]', ' ', texto_sem_acento)
    return ' '.join(texto_limpo.split()).upper()


def buscar_planos_do_usuario(supabase, usuario_id):
    """Busca no Supabase todos os planos/projetos vinculados ao usuário."""
    try:
        res = (
            supabase.table('lancamentos')
            .select('projeto_id')
            .eq('usuario_id', str(usuario_id))
            .execute()
        )
        if res and res.data:
            planos = sorted(
                list({str(item['projeto_id']) for item in res.data if item.get('projeto_id')}
            ))
            if planos:
                return planos
    except Exception as e:
        print(f'Erro ao buscar planos do usuário: {e}')
    return ['Padrão']


def verificar_limite_uso(supabase, usuario_id):
    """Verifica no Supabase se o usuário ainda possui cota de uso de voz no mês."""
    try:
        res = (
            supabase.table('usuarios')
            .select('*')
            .eq('id', usuario_id)
            .execute()
        )

        if res and hasattr(res, 'data') and len(res.data) > 0:
            dados_user = res.data[0]
            plano_ia = str(dados_user.get('plano_ia') or 'PADRAO').upper()
            uso_atual = int(dados_user.get('uso_voz_mes') or 0)
            limite_permitido = LIMITES_USO.get(plano_ia, 30)

            return uso_atual < limite_permitido, uso_atual, limite_permitido
    except Exception:
        pass
    return True, 0, 30


def incrementar_uso_voz(supabase, usuario_id, uso_atual):
    """Incrementa a contagem de uso após o áudio ser processado com sucesso."""
    try:
        supabase.table('usuarios').update({'uso_voz_mes': uso_atual + 1}).eq(
            'id', usuario_id
        ).execute()
    except Exception as e:
        print(f'Erro ao incrementar limite: {e}')


def transcrever_audio_groq(client_groq, audio_bytes):
    """Transcreve o áudio gravado usando o modelo Whisper no Groq."""
    transcription = client_groq.audio.transcriptions.create(
        file=('audio.wav', audio_bytes),
        model='whisper-large-v3-turbo',
        language='pt',
        response_format='text',
    )
    return transcription.strip()


def processar_texto_groq(
    client_groq, texto_transcrito, planos_disponiveis, plano_ativo=None
):
    """Processa o texto no Groq (Llama 3.3) para gerar a estrutura JSON."""
    plano_referencia = (
        plano_ativo
        if plano_ativo
        else (planos_disponiveis[0] if planos_disponiveis else 'Padrão')
    )

    prompt = f"""
    Você é o assistente financeiro do aplicativo ORCAS.
    Data de hoje: {date.today()}
    Plano ATUALMENTE SELECIONADO pelo usuário: "{plano_referencia}"
    Todos os planos disponíveis do usuário: {planos_disponiveis}

    O usuário falou o seguinte texto: "{texto_transcrito}"

    Analise o texto e responda EXCLUSIVAMENTE um objeto JSON válido:
    
    {{
      "transcricao": "{texto_transcrito}",
      "intencao": "REALIZAR" ou "PROJETAR" ou "CONSULTAR" ou "EXCLUIR",
      "projeto_id": "Nome/ID do plano citado se houver em {planos_disponiveis}. Se o usuário NÃO citar explicitamente outro plano, use EXATAMENTE '{plano_referencia}'",
      "descricao": "Nome limpo do lançamento sem pontuação desnecessária (Ex: Academia, S63 IPTU, Aluguel)",
      "valor": float_ou_null (retorne null ou 0.0 SE O USUÁRIO NÃO FALOU NENHUM VALOR MONETÁRIO OU SE A INTENÇÃO FOR EXCLUIR/CONSULTAR),
      "tipo": "Saída" ou "Entrada",
      "data_vencimento": "YYYY-MM-DD"
    }}
    """

    response = client_groq.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[{'role': 'user', 'content': prompt}],
        temperature=0.1,
        response_format={'type': 'json_object'},
    )

    texto_limpo = response.choices[0].message.content.strip()
    return json.loads(texto_limpo)


def buscar_planejamento_existente(supabase, usuario_id, projeto_id, descricao, incluir_realizados=False):
    """Busca lançamentos no Supabase priorizando correspondências por descrição."""
    if not descricao or len(descricao.strip()) < 2:
        return None

    try:
        desc_norm = normalizar_texto(descricao)

        query = (
            supabase.table('lancamentos')
            .select('*')
            .eq('usuario_id', str(usuario_id))
        )

        if not incluir_realizados:
            query = query.neq('status', 'Realizado')

        if projeto_id:
            query = query.eq('projeto_id', str(projeto_id))

        res = query.execute()

        if not res or not res.data:
            return None

        candidatos = res.data

        # Prioridade A: Correspondência exata da string normalizada
        for item in candidatos:
            d_banco = normalizar_texto(item.get('descricao', ''))
            if desc_norm == d_banco:
                return item

        # Prioridade B: Análise por palavras de peso
        palavras_busca = [p for p in desc_norm.split() if len(p) >= 2]
        melhor_candidato = None
        maior_pontuacao = 0

        for item in candidatos:
            d_banco = normalizar_texto(item.get('descricao', ''))
            palavras_banco = [p for p in d_banco.split() if len(p) >= 2]

            coincidencias = set(palavras_busca).intersection(set(palavras_banco))
            pontos = len(coincidencias)

            for termo in ['FINANC', 'ITAU', 'ADM', 'COND', 'IPTU', 'CEF', 'ACADEMIA']:
                if termo in d_banco and termo in desc_norm:
                    pontos += 2

            if pontos > maior_pontuacao:
                maior_pontuacao = pontos
                melhor_candidato = item

        if maior_pontuacao >= 1:
            return melhor_candidato

    except Exception as e:
        print(f'Erro na busca de planejamento: {e}')

    return None


def formatar_moeda_br(valor):
    """Auxiliar para formatar valores no padrão R$ 1.234,56."""
    try:
        val = float(valor or 0.0)
        return (
            f'R$ {val:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        )
    except Exception:
        return 'R$ 0,00'


def executar_acao_no_supabase(supabase, usuario_id, dados):
    """Executa inclusão, baixa ou exclusão no Supabase."""
    intencao = dados.get('intencao')
    projeto_id = str(dados.get('projeto_id'))
    descricao = dados.get('descricao')
    valor = float(dados.get('valor') or 0.0)
    data_hoje = date.today().strftime('%Y-%m-%d')
    tipo_fluxo = dados.get('tipo', 'Saída')
    if tipo_fluxo not in ['Entrada', 'Saída']:
        tipo_fluxo = 'Saída'

    id_existente = dados.get('id_existente')

    # AÇÃO: EXCLUIR
    if intencao == 'EXCLUIR':
        if id_existente:
            supabase.table('lancamentos').delete().eq('id', id_existente).execute()
            return f'🗑️ Lançamento **{descricao}** excluído com sucesso!'
        else:
            return f'⚠️ Não foi possível localizar o lançamento **{descricao}** para exclusão.'

    # AÇÃO: REALIZAR / CONSULTAR
    if intencao in ['REALIZAR', 'CONSULTAR']:
        if id_existente:
            payload_update = {
                'valor_real': valor,
                'status': 'Realizado',
            }
            supabase.table('lancamentos').update(payload_update).eq(
                'id', id_existente
            ).execute()
            return (
                f'✅ Lançamento **{descricao}** baixado como **Realizado** no'
                f' valor de {formatar_moeda_br(valor)}!'
            )
        else:
            payload_direto = {
                'projeto_id': projeto_id,
                'usuario_id': str(usuario_id),
                'descricao': descricao,
                'data': data_hoje,
                'data_vencimento': data_hoje,
                'tipo': tipo_fluxo,
                'valor_plan': 0,
                'valor_real': valor,
                'status': 'Realizado',
                'parcial_real': 0,
                'permite_parcial': False,
            }
            supabase.table('lancamentos').insert(payload_direto).execute()
            return (
                f'✅ Lançamento **{descricao}** ({formatar_moeda_br(valor)})'
                ' registrado e baixado com sucesso!'
            )

    # AÇÃO: PROJETAR
    elif intencao == 'PROJETAR':
        payload_proj = {
            'projeto_id': projeto_id,
            'usuario_id': str(usuario_id),
            'descricao': descricao,
            'data': data_hoje,
            'data_vencimento': dados.get('data_vencimento') or data_hoje,
            'tipo': tipo_fluxo,
            'valor_plan': valor,
            'valor_real': 0,
            'status': 'Planejado',
            'parcial_real': 0,
            'permite_parcial': False,
        }
        supabase.table('lancamentos').insert(payload_proj).execute()
        return (
            f'✅ Lançamento **{descricao}** ({formatar_moeda_br(valor)}) projetado'
            ' com sucesso!'
        )

    return 'Ação realizada com sucesso!'


def fechar_modal_voz():
    """Função auxiliar para resetar o estado e fechar o modal com segurança."""
    st.session_state.etapa_voz = 'gravacao'
    st.session_state.dados_interpretados = None
    st.session_state.hash_ultimo_audio = None
    st.session_state.audio_key_id = st.session_state.get('audio_key_id', 0) + 1
    st.session_state.abrir_modal_voz = False


@st.dialog('🎙️ Conversar com o ORCAS')
def exibir_modal_voz_orcas(supabase, id_usuario, planos_disponiveis=None):
    st.write('👋 **Olá! Em que posso ajudar nos seus lançamentos hoje?**')

    # Busca planos do usuário caso não tenham sido passados
    if not planos_disponiveis:
        planos_disponiveis = buscar_planos_do_usuario(supabase, id_usuario)

    plano_ativo = st.session_state.get('projeto_ativo') or st.session_state.get('plano_ativo')
    if not plano_ativo and planos_disponiveis:
        plano_ativo = planos_disponiveis[0]

    groq_key = st.secrets.get('GROQ_API_KEY')
    if not groq_key:
        st.error('❌ Chave GROQ_API_KEY não configurada nos Secrets do Streamlit!')
        return

    client_groq = Groq(api_key=groq_key.strip())

    if 'etapa_voz' not in st.session_state:
        st.session_state.etapa_voz = 'gravacao'
    if 'dados_interpretados' not in st.session_state:
        st.session_state.dados_interpretados = None
    if 'hash_ultimo_audio' not in st.session_state:
        st.session_state.hash_ultimo_audio = None
    if 'audio_key_id' not in st.session_state:
        st.session_state.audio_key_id = 0

    # ETAPA 1: GRAVAÇÃO E PROCESSAMENTO
    if st.session_state.etapa_voz == 'gravacao':
        pode_usar, uso_atual, limite_max = verificar_limite_uso(
            supabase, id_usuario
        )

        if not pode_usar:
            st.error(
                '⚠️ **Você atingiu o limite mensal do recurso de voz!**\n\n'
                f'Você utilizou **{uso_atual}/{limite_max}** comandos neste mês.'
            )
            return

        st.caption(
            f'📊 Uso do recurso de voz no mês: **{uso_atual}/{limite_max}** chamadas.'
        )

        key_audio = f'audio_input_{st.session_state.audio_key_id}'
        audio_input = st.audio_input('Grave seu comando abaixo:', key=key_audio)

        if audio_input is not None:
            audio_bytes = audio_input.getvalue()
            hash_atual = hash(audio_bytes)

            if hash_atual != st.session_state.hash_ultimo_audio:
                with st.spinner('🤖 ORCAS está processando o áudio...'):
                    try:
                        incrementar_uso_voz(supabase, id_usuario, uso_atual)

                        texto = transcrever_audio_groq(client_groq, audio_bytes)
                        dados = processar_texto_groq(
                            client_groq, texto, planos_disponiveis, plano_ativo
                        )

                        st.session_state.hash_ultimo_audio = hash_atual

                        if (
                            not dados.get('projeto_id')
                            or dados.get('projeto_id') not in planos_disponiveis
                        ):
                            dados['projeto_id'] = plano_ativo

                        intencao = dados.get('intencao')
                        incluir_realizados = (intencao == 'EXCLUIR')

                        item_existente = buscar_planejamento_existente(
                            supabase,
                            id_usuario,
                            dados.get('projeto_id'),
                            dados.get('descricao', ''),
                            incluir_realizados=incluir_realizados
                        )

                        valor_falado = float(dados.get('valor') or 0.0)

                        if item_existente:
                            dados['id_existente'] = item_existente.get('id')
                            desc_cadastrada = item_existente.get('descricao') or dados.get('descricao')
                            dados['descricao'] = desc_cadastrada

                            valor_planejado = float(
                                item_existente.get('valor_plan')
                                or item_existente.get('valor_real')
                                or item_existente.get('valor')
                                or 0.0
                            )

                            if intencao == 'EXCLUIR':
                                dados['mensagem_orcas'] = (
                                    f'Encontrei o lançamento **{desc_cadastrada}**'
                                    f' no valor de **{formatar_moeda_br(valor_planejado)}**.\n\n'
                                    'Deseja realmente **EXCLUIR** este lançamento?'
                                )
                            else:
                                dt_venc = (
                                    item_existente.get('data_vencimento')
                                    or item_existente.get('data')
                                    or '-'
                                )
                                if dt_venc != '-':
                                    try:
                                        dt_venc = datetime.strptime(
                                            str(dt_venc)[:10], '%Y-%m-%d'
                                        ).strftime('%d/%m/%Y')
                                    except Exception:
                                        pass

                                valor_final = (
                                    valor_falado if valor_falado > 0.0 else valor_planejado
                                )
                                dados['valor'] = valor_final

                                dados['mensagem_orcas'] = (
                                    f'Encontrei a conta **{desc_cadastrada}** com o valor'
                                    f' planejado de **{formatar_moeda_br(valor_planejado)}**'
                                    f' (Vencimento: **{dt_venc}**).\n\nEsta é a conta a que'
                                    ' você se refere e confirma a baixa?'
                                )

                        else:
                            dados['id_existente'] = None
                            dados['valor'] = valor_falado

                            if intencao == 'EXCLUIR':
                                dados['mensagem_orcas'] = (
                                    f'Não encontrei nenhum lançamento com o nome **{dados.get("descricao")}**'
                                    ' para ser excluído.'
                                )
                            elif valor_falado > 0.0:
                                dados['mensagem_orcas'] = (
                                    'Não encontrei um planejamento pendente para'
                                    f' **{dados.get("descricao")}**. Deseja realizar um novo'
                                    ' lançamento direto no valor de'
                                    f' **{formatar_moeda_br(valor_falado)}**?'
                                )
                            else:
                                dados['mensagem_orcas'] = (
                                    f'Não encontrei a conta **{dados.get("descricao")}** pendente'
                                    ' nos planejamentos e nenhum valor foi informado. Por favor,'
                                    ' tente novamente informando o valor pago.'
                                )

                        st.session_state.dados_interpretados = dados
                        st.session_state.etapa_voz = 'confirmacao'
                        st.rerun()

                    except Exception as e:
                        st.error(f'Erro no processamento: {e}')

    # ETAPA 2: CONFIRMAÇÃO DO USUÁRIO
    elif st.session_state.etapa_voz == 'confirmacao':
        dados = st.session_state.dados_interpretados or {}

        st.info(f'🗣️ **Você disse:** "{dados.get("transcricao", "")}"')

        with st.container(border=True):
            st.markdown(f"🤖 **ORCAS:** {dados.get('mensagem_orcas')}")
            st.markdown('---')

            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"• **Ação:** {dados.get('intencao', 'REALIZAR')}")
                st.write(f"• **Plano:** {dados.get('projeto_id') or 'Padrão'}")
                st.write(f"• **Descrição:** {dados.get('descricao', '-')}")
            with col_b:
                st.write(f"• **Tipo:** {dados.get('tipo', 'Saída')}")
                st.write(f"• **Valor:** {formatar_moeda_br(dados.get('valor'))}")

        st.markdown('---')
        btn_salvar, btn_refazer, btn_cancelar = st.columns(3)

        with btn_salvar:
            texto_botao = "🗑️ Confirmar Exclusão" if dados.get('intencao') == "EXCLUIR" else "✅ Confirmar e Gravar"
            if st.button(
                texto_botao, type='primary', use_container_width=True
            ):
                try:
                    msg_sucesso = executar_acao_no_supabase(
                        supabase, id_usuario, dados
                    )
                    st.success(msg_sucesso)

                    time.sleep(1.2)

                    # Garante que o modal fecha e desativa a flag de exibição
                    fechar_modal_voz()
                    st.rerun()
                except Exception as e:
                    st.error(f'❌ Erro ao processar ação: {e}')

        with btn_refazer:
            if st.button('🔄 Falar Novamente', use_container_width=True):
                st.session_state.etapa_voz = 'gravacao'
                st.session_state.dados_interpretados = None
                st.session_state.hash_ultimo_audio = None
                st.session_state.audio_key_id += 1
                st.rerun()

        with btn_cancelar:
            if st.button('❌ Cancelar / Sair', use_container_width=True):
                fechar_modal_voz()
                st.rerun()