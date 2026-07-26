import json
from datetime import date, datetime
import streamlit as st
from google import genai
from google.genai import types

LIMITES_USO = {
    'PADRAO': 30,          # 30 interações de voz/mês
    'INTERMEDIARIO': 100,  # 100 interações de voz/mês
    'ILIMITADO': 999999,   # Sem limite
}


def verificar_e_incrementar_limite(supabase, usuario_id):
    """Verifica no Supabase se o usuário ainda tem cota de uso de voz disponível no mês."""
    try:
        res = supabase.table('usuarios').select('*').eq('id', usuario_id).execute()

        if res and hasattr(res, 'data') and len(res.data) > 0:
            dados_user = res.data[0]
            plano_ia = str(dados_user.get('plano_ia') or 'PADRAO').upper()
            uso_atual = int(dados_user.get('uso_voz_mes') or 0)
            limite_permitido = LIMITES_USO.get(plano_ia, 30)

            if uso_atual >= limite_permitido:
                return False, uso_atual, limite_permitido

            try:
                novo_uso = uso_atual + 1
                supabase.table('usuarios').update({'uso_voz_mes': novo_uso}).eq(
                    'id', usuario_id
                ).execute()
            except Exception:
                pass

            return True, uso_atual + 1, limite_permitido

    except Exception:
        return True, 0, 30

    return True, 0, 30


def processar_comando_voz(audio_bytes, planos_disponiveis):
    """Processa o áudio utilizando a SDK oficial com o modelo estável mais atual."""
    api_key = st.secrets.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError('Chave GEMINI_API_KEY não encontrada nos Secrets!')

    client = genai.Client(api_key=api_key)

    prompt = f"""
    Você é o assistente financeiro de voz do aplicativo ORCAS.
    Data de hoje: {date.today()}
    Planos ativos cadastrados pelo usuário: {planos_disponiveis}

    Analise o áudio e responda EXCLUSIVAMENTE um objeto JSON válido (sem markdown ou textos adicionais):
    
    {{
      "transcricao": "Texto exato falado pelo usuário",
      "intencao": "REALIZAR" ou "PROJETAR" ou "CONSULTAR",
      "projeto_id": "Nome/ID do plano citado pelo usuário. Se não citado e houver 1 plano ativo, use ele",
      "descricao": "Termo de busca/descrição limpa da conta (ex: Celular Claro, Aluguel, Supermercado)",
      "valor": float_ou_null,
      "tipo": "Saida" ou "Entrada",
      "data_vencimento": "YYYY-MM-DD"
    }}
    """

    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type='audio/wav')

    # Passa o nome limpo do modelo ativo
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[prompt, audio_part]
    )

    texto_limpo = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(texto_limpo)


def buscar_planejamento_existente(supabase, usuario_id, projeto_id, descricao):
    """Busca na tabela de lançamentos se já existe uma conta planejada/pendente correspondente."""
    try:
        query = (
            supabase.table('lancamentos')
            .select('*')
            .eq('usuario_id', usuario_id)
            .ilike('descricao', f'%{descricao}%')
        )

        if projeto_id:
            query = query.eq('projeto_id', projeto_id)

        res = query.execute()

        if res and res.data:
            planejados = [
                l
                for l in res.data
                if not l.get('realizado') and l.get('status') != 'Realizado'
            ]
            if planejados:
                return planejados[0]
            return res.data[0]

    except Exception as e:
        print(f'Erro na busca prévia: {e}')

    return None


def executar_acao_no_supabase(supabase, usuario_id, dados):
    """Efetiva a gravação ou atualização na tabela 'lancamentos'."""
    intencao = dados.get('intencao')
    projeto_id = dados.get('projeto_id')
    descricao = dados.get('descricao')
    valor = float(dados.get('valor') or 0.0)
    data_venc = dados.get('data_vencimento') or str(date.today())
    tipo_fluxo = dados.get('tipo', 'Saida')
    id_lancamento_existente = dados.get('id_existente')

    # 1. REALIZAR / CONCILIAR
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
                f'✅ Lançamento **{descricao}** marcado como **REALIZADO** no valor'
                f' de R$ {valor:,.2f}!'
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
                f'✅ Lançamento de **{descricao}** (R$ {valor:,.2f}) realizado e baixado'
                ' com sucesso!'
            )

    # 2. PROJETAR UM NOVO LANÇAMENTO
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
        return f'✅ Lançamento **{descricao}** (R$ {valor:,.2f}) projetado com sucesso!'

    return 'Ação concluída com sucesso!'


@st.dialog('🎙️ Conversar com o ORCAS')
def exibir_modal_voz_orcas(supabase, id_usuario, planos_disponiveis):
    """Modal de interface com verificação cruzada de dados no banco antes de confirmar."""
    st.write('👋 **Olá! Em que posso ajudar nos seus lançamentos hoje?**')

    if 'etapa_voz' not in st.session_state:
        st.session_state.etapa_voz = 'gravacao'
    if 'dados_interpretados' not in st.session_state:
        st.session_state.dados_interpretados = None

    # ETAPA 1: GRAVAÇÃO E PROCESSAMENTO
    if st.session_state.etapa_voz == 'gravacao':
        pode_usar, uso_atual, limite_max = verificar_e_incrementar_limite(
            supabase, id_usuario
        )

        if not pode_usar:
            st.error(
                f'⚠️ **Você atingiu o limite mensal do recurso de voz!**\n\nVocê'
                f' utilizou **{uso_atual}/{limite_max}** comandos neste mês.\nFaça um'
                ' upgrade de plano na tela de **Gestão / Configurações** para'
                ' expandir seu limite.'
            )
            return

        st.caption(
            f'📊 Uso do recurso de voz no mês: **{uso_atual}/{limite_max}**'
            ' chamadas.'
        )

        audio_input = st.audio_input('Grave seu comando abaixo:')

        if audio_input:
            with st.spinner(
                '🤖 ORCAS está processando o áudio e checando seus'
                ' planejamentos...'
            ):
                try:
                    audio_bytes = audio_input.getvalue()
                    dados = processar_comando_voz(audio_bytes, planos_disponiveis)

                    if not dados.get('projeto_id') and len(planos_disponiveis) == 1:
                        dados['projeto_id'] = planos_disponiveis[0]

                    # Checagem na tabela de lançamentos do Supabase
                    item_existente = buscar_planejamento_existente(
                        supabase,
                        id_usuario,
                        dados.get('projeto_id'),
                        dados.get('descricao', ''),
                    )

                    if item_existente:
                        dados['id_existente'] = item_existente.get('id')
                        if not dados.get('valor') or dados.get('valor') == 0:
                            dados['valor'] = (
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

                        dados['mensagem_orcas'] = (
                            f"Entendi que você pagou a conta **{item_existente.get('descricao')}**."
                            ' Chequei no sistema e verifiquei que estava planejado o valor'
                            f" de **R$ {float(dados['valor']):,.2f}** com vencimento em"
                            f' **{dt_venc}**. Você confirma?'
                        )
                    else:
                        dados['id_existente'] = None
                        valor_audio = float(dados.get('valor') or 0.0)
                        dados['mensagem_orcas'] = (
                            f"Entendi que você quer registrar **{dados.get('descricao')}**"
                            f' no valor de **R$ {valor_audio:,.2f}**. Não encontrei um'
                            ' planejamento prévio, então realizarei um novo lançamento'
                            ' direto. Você confirma?'
                        )

                    st.session_state.dados_interpretados = dados
                    st.session_state.etapa_voz = 'confirmacao'
                    st.rerun()

                except Exception as e:
                    st.error(
                        'Não foi possível processar o áudio. Tente novamente.'
                        f' (Detalhes: {e})'
                    )

    # ETAPA 2: CONFIRMAÇÃO
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
                valor_fmt = (
                    f"R$ {float(dados.get('valor') or 0.0):,.2f}".replace(',', 'X')
                    .replace('.', ',')
                    .replace('X', '.')
                )
                st.write(f"• **Valor:** {valor_fmt}")

        st.markdown('---')
        btn_salvar, btn_refazer = st.columns(2)

        with btn_salvar:
            if st.button(
                '✅ Confirmar e Gravar', type='primary', use_container_width=True
            ):
                msg_sucesso = executar_acao_no_supabase(supabase, id_usuario, dados)
                st.success(msg_sucesso)

                st.session_state.etapa_voz = 'gravacao'
                st.session_state.dados_interpretados = None
                st.rerun()

        with btn_refazer:
            if st.button('🔄 Falar Novamente', use_container_width=True):
                st.session_state.etapa_voz = 'gravacao'
                st.session_state.dados_interpretados = None
                st.rerun()