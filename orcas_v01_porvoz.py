from datetime import date, datetime
import json
import re
import time
import unicodedata
from groq import Groq
import streamlit as st

# Limites mensais de uso do recurso por voz
LIMITES_USO = {
    'PADRAO': 30,  # 30 interações de voz/mês
    'INTERMEDIARIO': 100,  # 100 interações de voz/mês
    'ILIMITADO': 999999,  # Sem limite
}


def normalizar_texto(texto):
    """Remove acentos, pontos, traços e converte para maiúsculo para comparação precisa."""
    if not texto:
        return ''
    nfkd = unicodedata.normalize('NFKD', str(texto))
    texto_sem_acento = ''.join([c for c in nfkd if not unicodedata.combining(c)])
    # Mantém apenas letras e números
    texto_limpo = re.sub(r'[^a-zA-Z0-9\s]', ' ', texto_sem_acento)
    return ' '.join(texto_limpo.split()).upper()


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
    """Processa o texto no Groq (Llama 3.3) para gerar a estrutura JSON priorizando o plano ativo."""
    plano_referencia = (
        plano_ativo
        if plano_ativo
        else (planos_disponiveis[0] if planos_disponiveis else 'Padrão')
    )

    prompt = f"""
    Você é o assistente financeiro do aplicativo ORCAS.
    Data de hoje: {date.today()}
    Plano ATUALMENTE SELECIONADO pelo usuário: "{plano_referencia}"
    Todos os planos disponíveis: {planos_disponiveis}

    O usuário falou o seguinte texto: "{texto_transcrito}"

    Analise o texto e responda EXCLUSIVAMENTE um objeto JSON válido (sem markdown ou formatações externas):
    
    {{
      "transcricao": "{texto_transcrito}",
      "intencao": "REALIZAR" ou "PROJETAR" ou "CONSULTAR",
      "projeto_id": "Nome/ID do plano citado. Se o usuário NÃO citar explicitamente outro plano, use EXATAMENTE '{plano_referencia}'",
      "descricao": "Termo de busca/descrição limpa da conta (ex: Celular Claro, Aluguel, Supermercado, S63 Financ Itau)",
      "valor": float_ou_null (retorne null ou 0.0 SE O USUÁRIO NÃO FALOU UM VALOR MONETÁRIO),
      "tipo": "Saida" ou "Entrada",
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


def buscar_planejamento_existente(supabase, usuario_id, projeto_id, descricao):
    """Busca rigorosa de lançamentos pendentes (NÃO realizados e com valor realizado zerado)."""
    if not descricao or len(descricao.strip()) < 2:
        return None

    try:
        desc_buscada_norm = normalizar_texto(descricao)
        palavras_busca = [p for p in desc_buscada_norm.split() if len(p) >= 2]

        if not palavras_busca:
            return None

        query = (
            supabase.table('lancamentos')
            .select('*')
            .eq('usuario_id', usuario_id)
        )
        if projeto_id:
            query = query.eq('projeto_id', projeto_id)

        res = query.execute()

        if not res or not res.data:
            return None

        # REGRA CRÍTICA: Filtrar APENAS contas pendentes de fato
        # (realizado == False, status PLAN e valor_realizado == 0)
        pendentes = []
        for l in res.data:
            is_realizado = l.get('realizado') is True
            status = str(l.get('status') or '').strip().upper()
            val_real = float(l.get('valor_realizado') or l.get('valor_real') or 0.0)

            if not is_realizado and status != 'REALIZADO' and val_real == 0:
                pendentes.append(l)

        candidatos_avaliados = []

        for item in pendentes:
            desc_banco_norm = normalizar_texto(item.get('descricao', ''))
            palavras_banco = [p for p in desc_banco_norm.split() if len(p) >= 2]

            # 1. Match exato normalizado (Ex: "S63 FINANC ITAU" == "S63 FINANC ITAU")
            if desc_buscada_norm == desc_banco_norm:
                return item

            # 2. Se todas as palavras faladas estiverem contidas na descrição do banco
            if all(p in desc_banco_norm for p in palavras_busca):
                candidatos_avaliados.append((100, item))
                continue

            # 3. Pontuação por coincidência de termos (dando peso extra para palavras raras/específicas)
            coincidencias = set(palavras_busca).intersection(set(palavras_banco))
            if coincidencias:
                score = len(coincidencias)
                # Se coincidir termos fortes como 'FINANC' ou 'FINANQ', aumenta a relevância
                candidatos_avaliados.append((score, item))

        if candidatos_avaliados:
            candidatos_avaliados.sort(key=lambda x: x[0], reverse=True)
            return candidatos_avaliados[0][1]

    except Exception as e:
        print(f'Erro na busca de planejamento: {e}')

    return None


def formatar_moeda_br(valor):
    """Auxiliar para formatar valores no padrão brasileiro R$ 1.234,56."""
    try:
        val = float(valor or 0.0)
        return (
            f'R$ {val:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        )
    except Exception:
        return 'R$ 0,00'


def executar_acao_no_supabase(supabase, usuario_id, dados):
    """Executa a persistência dos dados no banco Supabase após confirmação."""
    intencao = dados.get('intencao')
    projeto_id = dados.get('projeto_id')
    descricao = dados.get('descricao')
    valor = float(dados.get('valor') or 0.0)
    data_venc = dados.get('data_vencimento') or str(date.today())
    tipo_fluxo = dados.get('tipo', 'Saida')
    id_lancamento_existente = dados.get('id_existente')

    if intencao == 'REALIZAR':
        if id_lancamento_existente:
            payload_update = {
                'realizado': True,
                'status': 'Realizado',
                'valor_realizado': valor,
                'valor_real': valor,
                'parcial_data': str(date.today()),
            }
            supabase.table('lancamentos').update(payload_update).eq(
                'id', id_lancamento_existente
            ).execute()
            return (
                f'✅ Lançamento **{descricao}** baixado como **REALIZADO** no valor'
                f' de {formatar_moeda_br(valor)}!'
            )
        else:
            payload_direto = {
                'usuario_id': usuario_id,
                'projeto_id': projeto_id,
                'descricao': descricao,
                'valor': valor,
                'valor_plan': valor,
                'valor_realizado': valor,
                'valor_real': valor,
                'tipo': tipo_fluxo,
                'data_vencimento': data_venc,
                'data': str(date.today()),
                'realizado': True,
                'status': 'Realizado',
            }
            supabase.table('lancamentos').insert(payload_direto).execute()
            return (
                f'✅ Lançamento **{descricao}** ({formatar_moeda_br(valor)})'
                ' registrado e baixado com sucesso!'
            )

    elif intencao == 'PROJETAR':
        payload = {
            'usuario_id': usuario_id,
            'projeto_id': projeto_id,
            'descricao': descricao,
            'valor': valor,
            'valor_plan': valor,
            'tipo': tipo_fluxo,
            'data_vencimento': data_venc,
            'data': data_venc,
            'realizado': False,
            'status': 'Planejado',
            'valor_realizado': 0.0,
            'valor_real': 0.0,
        }
        supabase.table('lancamentos').insert(payload).execute()
        return (
            f'✅ Lançamento **{descricao}** ({formatar_moeda_br(valor)}) projetado'
            ' com sucesso!'
        )

    return 'Ação concluída com sucesso!'


@st.dialog('🎙️ Conversar com o ORCAS')
def exibir_modal_voz_orcas(supabase, id_usuario, planos_disponiveis=None):
    """Modal de interface por voz sem o crash de empacotamento do Streamlit (*args/**kwargs removidos da assinatura)."""
    st.write('👋 **Olá! Em que posso ajudar nos seus lançamentos hoje?**')

    if planos_disponiveis is None:
        planos_disponiveis = []

    plano_ativo = st.session_state.get('projeto_ativo') or st.session_state.get(
        'plano_ativo'
    )
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

    # ------------------ ETAPA 1: GRAVAÇÃO E INTERPRETAÇÃO ------------------
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
            f'📊 Uso do recurso de voz no mês: **{uso_atual}/{limite_max}**'
            ' chamadas.'
        )

        key_audio = f'audio_input_{st.session_state.audio_key_id}'
        audio_input = st.audio_input('Grave seu comando abaixo:', key=key_audio)

        if audio_input is not None:
            audio_bytes = audio_input.getvalue()
            hash_atual = hash(audio_bytes)

            if hash_atual != st.session_state.hash_ultimo_audio:
                with st.spinner('🤖 ORCAS está processando o áudio...'):
                    try:
                        # Incrementa apenas na execução do áudio
                        incrementar_uso_voz(supabase, id_usuario, uso_atual)

                        # 1. Transcrição do áudio via Whisper
                        texto = transcrever_audio_groq(client_groq, audio_bytes)

                        # 2. Extração estruturada (JSON) via Llama 3.3
                        dados = processar_texto_groq(
                            client_groq, texto, planos_disponiveis, plano_ativo
                        )

                        st.session_state.hash_ultimo_audio = hash_atual

                        if (
                            not dados.get('projeto_id')
                            or dados.get('projeto_id') not in planos_disponiveis
                        ):
                            dados['projeto_id'] = plano_ativo

                        # 3. Consulta Inteligente ao Supabase
                        item_existente = buscar_planejamento_existente(
                            supabase,
                            id_usuario,
                            dados.get('projeto_id'),
                            dados.get('descricao', ''),
                        )

                        valor_falado = float(dados.get('valor') or 0.0)

                        if item_existente:
                            dados['id_existente'] = item_existente.get('id')
                            desc_cadastrada = item_existente.get(
                                'descricao'
                            ) or dados.get('descricao')
                            valor_planejado = float(
                                item_existente.get('valor_plan')
                                or item_existente.get('valor')
                                or 0.0
                            )

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

                            if valor_falado == 0.0:
                                dados['valor'] = valor_planejado
                                dados['mensagem_orcas'] = (
                                    f'Encontrei a conta **{desc_cadastrada}** com o valor'
                                    ' planejado de'
                                    f' **{formatar_moeda_br(valor_planejado)}** (Vencimento:'
                                    f' **{dt_venc}**).\n\nEsta é a conta a que você se refere e'
                                    ' confirma a baixa?'
                                )
                            else:
                                dados['valor'] = valor_falado
                                dados['mensagem_orcas'] = (
                                    f'Encontrei a conta **{desc_cadastrada}** (Planejado:'
                                    f' {formatar_moeda_br(valor_planejado)}).\n\nConfirmar a'
                                    f' baixa no valor de **{formatar_moeda_br(valor_falado)}**?'
                                )

                        else:
                            dados['id_existente'] = None
                            dados['valor'] = valor_falado
                            if valor_falado > 0.0:
                                dados['mensagem_orcas'] = (
                                    'Não encontrei um planejamento prévio para'
                                    f' **{dados.get("descricao")}**. Deseja realizar um novo'
                                    ' lançamento direto no valor de'
                                    f' **{formatar_moeda_br(valor_falado)}**?'
                                )
                            else:
                                dados['mensagem_orcas'] = (
                                    f'Não encontrei a conta **{dados.get("descricao")}** nos'
                                    ' planejamentos e nenhum valor foi informado. Por favor,'
                                    ' tente novamente informando o valor.'
                                )

                        st.session_state.dados_interpretados = dados
                        st.session_state.etapa_voz = 'confirmacao'
                        st.rerun()

                    except Exception as e:
                        st.error(f'Erro no processamento: {e}')

    # ------------------ ETAPA 2: CONFIRMAÇÃO DO USUÁRIO ------------------
    elif st.session_state.etapa_voz == 'confirmacao':
        dados = st.session_state.dados_interpretados or {}

        st.info(f'🗣️ **Você disse:** "{dados.get("transcricao", "")}"')

        with st.container(border=True):
            st.markdown(f"🤖 **ORCAS:** {dados.get('mensagem_orcas')}")
            st.markdown('---')

            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"• **Ação:** {dados.get('intencao', '-')}")
                st.write(f"• **Plano:** {dados.get('projeto_id') or 'Padrão'}")
                st.write(f"• **Descrição:** {dados.get('descricao', '-')}")
            with col_b:
                st.write(f"• **Tipo:** {dados.get('tipo', 'Saida')}")
                st.write(f"• **Valor:** {formatar_moeda_br(dados.get('valor'))}")

        st.markdown('---')
        btn_salvar, btn_refazer = st.columns(2)

        with btn_salvar:
            if st.button(
                '✅ Confirmar e Gravar', type='primary', use_container_width=True
            ):
                try:
                    msg_sucesso = executar_acao_no_supabase(supabase, id_usuario, dados)
                    st.success(msg_sucesso)

                    time.sleep(1.5)

                    st.session_state.etapa_voz = 'gravacao'
                    st.session_state.dados_interpretados = None
                    st.session_state.hash_ultimo_audio = None
                    st.session_state.audio_key_id += 1
                    st.rerun()
                except Exception as e:
                    st.error(f'❌ Erro ao gravar lançamento: {e}')

        with btn_refazer:
            if st.button('🔄 Falar Novamente', use_container_width=True):
                st.session_state.etapa_voz = 'gravacao'
                st.session_state.dados_interpretados = None
                st.session_state.hash_ultimo_audio = None
                st.session_state.audio_key_id += 1
                st.rerun()