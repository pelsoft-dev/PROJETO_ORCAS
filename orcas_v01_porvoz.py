from datetime import date, datetime, timedelta
import json
import re
import time
import unicodedata
import zoneinfo
from groq import Groq
import streamlit as st

try:
    from modulo_conciliacao import (
        buscar_planejamento_conciliacao,
        processar_baixa_ou_lancamento_conciliacao,
    )
except ImportError:
    pass

LIMITES_USO = {"PADRÃO": 30, "INTERMEDIÁRIO": 100, "ILIMITADO": 999999}


def obter_hoje_brasil():
    fuso_br = zoneinfo.ZoneInfo("America/Sao_Paulo")
    return datetime.now(fuso_br).date()


def verificar_limite_uso(supabase, usuario_id):
    try:
        res = (
            supabase.table("usuarios")
            .select("*")
            .eq("id", usuario_id)
            .execute()
        )
        if res and hasattr(res, "data") and len(res.data) > 0:
            dados_user = res.data[0]
            plano_ia = str(dados_user.get("plano_ia") or "PADRAO").upper()
            uso_atual = int(dados_user.get("uso_voz_mes") or 0)
            limite_permitido = LIMITES_USO.get(plano_ia, 30)
            return uso_atual < limite_permitido, uso_atual, limite_permitido
    except Exception:
        pass
    return True, 0, 30


def incrementar_uso_voz(supabase, usuario_id, uso_atual):
    try:
        supabase.table("usuarios").update({"uso_voz_mes": uso_atual + 1}).eq(
            "id", usuario_id
        ).execute()
    except Exception as e:
        print(f"Erro ao incrementar limite: {e}")


def transcrever_audio_groq(client_groq, audio_bytes):
    transcription = client_groq.audio.transcriptions.create(
        file=("audio.wav", audio_bytes),
        model="whisper-large-v3-turbo",
        language="pt",
        response_format="text",
    )
    return transcription.strip()


def processar_texto_groq(
    client_groq, texto_transcrito, planos_disponiveis, plano_ativo=None
):
    plano_referencia = (
        plano_ativo
        if plano_ativo
        else (planos_disponiveis[0] if planos_disponiveis else "Padrão")
    )
    hoje_dt = obter_hoje_brasil()

    prompt = f"""
    Você é o módulo de escuta por voz do ORCAS. Traduza a fala do usuário no formato de intenção para o motor de conciliação.
    Data HOJE: {hoje_dt.strftime('%Y-%m-%d')}
    Plano ATUAL: "{plano_referencia}"
    Planos DISPONÍVEIS: {planos_disponiveis}
    ÁUDIO: "{texto_transcrito}"

    REGRAS DE CLASSIFICAÇÃO:
    - Verbos no passado ("comprei", "paguei", "fiz"): intencao = "REALIZAR"
    - Verbos ou ideias futuras ("vou comprar", "agendar", "projetar"): intencao = "PROJETAR"
    - Se citar cartão ou bandeira ("visa", "master", "cartão", "itau"): preencher "cartao"
    - Se citar parcelas ("em 3x", "parcelado em 5 vezes"): preencher "parcelas" (int)

    Responda EXCLUSIVAMENTE um JSON:
    {{
      "transcricao": "{texto_transcrito}",
      "intencao": "REALIZAR" | "PROJETAR" | "PARCIAL" | "ALTERAR" | "EXCLUIR",
      "projeto_id": "{plano_referencia}",
      "descricao": "Item ou Serviço",
      "valor": float_ou_null,
      "tipo": "Saída",
      "data_vencimento": "{hoje_dt.strftime('%Y-%m-%d')}",
      "permite_parcial": false,
      "cartao": string_ou_null,
      "parcelas": int
    }}
    """

    # Ajustado modelo estável da Groq (evita o erro 404 da imagem)
    response = client_groq.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content.strip())


def fechar_modal_voz():
    st.session_state.etapa_voz = "gravacao"
    st.session_state.dados_interpretados = None
    st.session_state.hash_ultimo_audio = None
    st.session_state.audio_key_id = st.session_state.get("audio_key_id", 0) + 1
    # DESATIVA A FLAG PARA NÃO CONTINUAR REABRINDO NAS OUTRAS TELAS
    st.session_state.abrir_modal_voz = False


@st.dialog("🎙️ Conversar com o ORCAS")
def exibir_modal_voz_orcas(supabase, id_usuario, planos_disponiveis=None):
    st.write("👋 **Olá! O que deseja lançar ou conciliar agora?**")

    plano_ativo = st.session_state.get("projeto_ativo") or "Padrão"
    groq_key = st.secrets.get("GROQ_API_KEY")

    if not groq_key:
        st.error("❌ GROQ_API_KEY não configurada.")
        fechar_modal_voz()
        return

    client_groq = Groq(api_key=groq_key.strip())

    if "etapa_voz" not in st.session_state:
        st.session_state.etapa_voz = "gravacao"
    if "dados_interpretados" not in st.session_state:
        st.session_state.dados_interpretados = None

    if st.session_state.etapa_voz == "gravacao":
        pode_usar, uso_atual, limite_max = verificar_limite_uso(supabase, id_usuario)
        if not pode_usar:
            st.error(f"⚠️ Limite mensal de voz atingido ({uso_atual}/{limite_max}).")
            if st.button("Fechar"):
                fechar_modal_voz()
                st.rerun()
            return

        key_audio = f"audio_input_{st.session_state.get('audio_key_id', 0)}"
        audio_input = st.audio_input("Grave seu comando:", key=key_audio)

        if audio_input is not None:
            audio_bytes = audio_input.getvalue()
            with st.spinner("🤖 Interpretando voz para a conciliação..."):
                try:
                    incrementar_uso_voz(supabase, id_usuario, uso_atual)
                    texto = transcrever_audio_groq(client_groq, audio_bytes)
                    dados = processar_texto_groq(
                        client_groq, texto, planos_disponiveis, plano_ativo
                    )

                    item_existente = None
                    if 'buscar_planejamento_conciliacao' in globals():
                        item_existente = buscar_planejamento_conciliacao(
                            supabase, id_usuario, dados
                        )

                    if item_existente:
                        dados["id_existente"] = item_existente.get("id")
                        dados["mensagem_orcas"] = (
                            f"Localizei a conta **{item_existente.get('descricao')}** orçada "
                            f"no valor de R$ {item_existente.get('valor_plan'):,.2f}. Confirmar a baixa pela conciliação?"
                        )
                    else:
                        dados["id_existente"] = None
                        dados["mensagem_orcas"] = (
                            f"Não encontrei conta orçada pendente para **{dados.get('descricao')}**. "
                            f"Deseja realizar o lançamento direto via conciliação?"
                        )

                    st.session_state.dados_interpretados = dados
                    st.session_state.etapa_voz = "confirmacao"
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro no processamento da voz: {e}")

    elif st.session_state.etapa_voz == "confirmacao":
        dados = st.session_state.dados_interpretados or {}
        st.info(f'🗣️ **Comando:** "{dados.get("transcricao", "")}"')

        with st.container(border=True):
            st.markdown(f"🤖 **ORCAS:** {dados.get('mensagem_orcas')}")

            with st.form("form_confirmacao_orcas"):
                nova_descricao = st.text_input("Descrição", value=dados.get("descricao", ""))
                novo_valor = st.number_input("Valor (R$)", value=float(dados.get("valor") or 0.0))
                nova_intencao = st.selectbox(
                    "Ação", ["REALIZAR", "PROJETAR", "PARCIAL", "ALTERAR", "EXCLUIR"],
                    index=0 if dados.get("intencao") == "REALIZAR" else 1
                )

                submit_salvar = st.form_submit_button("✅ Processar na Conciliação", type="primary")

            if submit_salvar:
                dados["descricao"] = nova_descricao
                dados["valor"] = novo_valor
                dados["intencao"] = nova_intencao

                try:
                    if 'processar_baixa_ou_lancamento_conciliacao' in globals():
                        msg_sucesso = processar_baixa_ou_lancamento_conciliacao(
                            supabase, id_usuario, dados
                        )
                        st.success(msg_sucesso)
                    else:
                        st.session_state["porvoz_descricao"] = dados.get("descricao")
                        st.session_state["porvoz_valor"] = f"{float(dados.get('valor') or 0.0):,.2f}".replace(".", ",")
                        st.session_state["porvoz_tipo"] = dados.get("tipo", "Saída")
                        st.session_state["porvoz_acao"] = "sem_planejamento"
                        st.session_state["payload_conciliacao_pendente"] = dados
                        st.success("✅ Dados enviados com sucesso para a Conciliação!")

                    time.sleep(0.5)
                    fechar_modal_voz()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao conciliar: {e}")