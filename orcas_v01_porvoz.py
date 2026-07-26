import streamlit as st
import google.generativeai as genai
from datetime import datetime, date
import json

# --- CONFIGURAÇÃO DA API DO GEMINI ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# Tabela de limites configuráveis por plano
LIMITES_USO = {
    "PADRAO": 30,          # 30 interações de voz/mês
    "INTERMEDIARIO": 100,  # 100 interações de voz/mês
    "ILIMITADO": 999999    # Sem limite prático
}


def verificar_e_incrementar_limite(supabase, usuario_id):
    """
    Verifica no Supabase se o usuário (tabela 'usuarios') ainda tem cota disponível.
    Adapta-se ao campo de plano e cota (caso ainda não existam no schema, trata com fallback).
    """
    try:
        res = supabase.table("usuarios").select("*").eq("id", usuario_id).execute()
        
        if res and hasattr(res, 'data') and len(res.data) > 0:
            dados_user = res.data[0]
            
            # Leitura com fallback para schemas legados
            plano_ia = str(dados_user.get("plano_ia") or "PADRAO").upper()
            uso_atual = int(dados_user.get("uso_voz_mes") or 0)
            limite_permitido = LIMITES_USO.get(plano_ia, 30)

            if uso_atual >= limite_permitido:
                return False, uso_atual, limite_permitido

            # Incrementa o uso no Supabase
            try:
                novo_uso = uso_atual + 1
                supabase.table("usuarios").update({"uso_voz_mes": novo_uso}).eq("id", usuario_id).execute()
            except Exception:
                pass # Evita travar caso a coluna ainda não tenha sido criada no Supabase
                
            return True, uso_atual + 1, limite_permitido
            
    except Exception as e:
        return True, 0, 30

    return True, 0, 30


def processar_comando_voz(audio_bytes, planos_disponiveis):
    """
    Envia o áudio ao Gemini e retorna a transcrição com os dados mapeados em JSON.
    """
    model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
    Você é o assistente financeiro de voz do aplicativo ORCAS.
    Data de hoje: {date.today()}
    Planos ativos cadastrados pelo usuário: {planos_disponiveis}

    Analise o áudio e responda EXCLUSIVAMENTE um objeto JSON válido (sem textos explicativos ou markdown):
    
    {{
      "transcricao": "Texto exato falado no áudio pelo usuário",
      "intencao": "PROJETAR" ou "REALIZAR" ou "CONSULTAR",
      "projeto_id": "Qual dos planos ativos o usuário citou (caso não citado e houver apenas 1, use ele. Se ambíguo, retorne null)",
      "descricao": "Descrição limpa do lançamento (ex: Aluguel, Celular, Supermercado, Salário)",
      "valor": float_ou_null,
      "tipo": "Entrada" ou "Saida",
      "data_vencimento": "YYYY-MM-DD",
      "realizado": true ou false,
      "resposta_orcas": "Mensagem curta e amigável confirmando o entendimento"
    }}
    """

    response = model.generate_content([
        prompt,
        {
            "mime_type": "audio/wav",
            "data": audio_bytes
        }
    ])

    texto_limpo = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(texto_limpo)


def executar_acao_no_supabase(supabase, usuario_id, dados):
    """
    Persiste os dados na tabela 'lancamentos' do ORCAS.
    """
    intencao = dados.get("intencao")
    projeto_id = dados.get("projeto_id")
    descricao = dados.get("descricao")
    valor = float(dados.get("valor") or 0.0)
    data_venc = dados.get("data_vencimento") or str(date.today())
    tipo_fluxo = dados.get("tipo", "Saida")

    # 1. PROJETAR UM NOVO LANÇAMENTO (INSERT)
    if intencao == "PROJETAR":
        payload = {
            "usuario_id": usuario_id,
            "projeto_id": projeto_id,
            "descricao": descricao,
            "valor": valor,
            "valor_plan": valor,
            "tipo": tipo_fluxo,
            "data_vencimento": data_venc,
            "data": data_venc,
            "realizado": False,
            "status": "Planejado",
            "valor_realizado": 0.0,
            "valor_real": 0.0
        }
        supabase.table("lancamentos").insert(payload).execute()
        return f"✅ Lançamento **{descricao}** (R$ {valor:,.2f}) projetado com sucesso!"

    # 2. REALIZAR / CONCILIAR (UPDATE OU INSERT DIRETO)
    elif intencao == "REALIZAR":
        res = supabase.table("lancamentos")\
            .select("*")\
            .eq("usuario_id", usuario_id)\
            .eq("projeto_id", projeto_id)\
            .ilike("descricao", f"%{descricao}%")\
            .execute()

        if res and res.data:
            id_lancamento = res.data[0]["id"]
            payload_update = {
                "realizado": True,
                "status": "Realizado",
                "valor_realizado": valor,
                "valor_real": valor,
                "parcial_data": str(date.today())
            }
            supabase.table("lancamentos").update(payload_update).eq("id", id_lancamento).execute()
            return f"✅ Lançamento **{descricao}** marcado como **REALIZADO** no valor de R$ {valor:,.2f}!"
        else:
            payload_direto = {
                "usuario_id": usuario_id,
                "projeto_id": projeto_id,
                "descricao": descricao,
                "valor": valor,
                "valor_plan": valor,
                "valor_realizado": valor,
                "valor_real": valor,
                "tipo": tipo_fluxo,
                "data_vencimento": data_venc,
                "data": str(date.today()),
                "realizado": True,
                "status": "Realizado"
            }
            supabase.table("lancamentos").insert(payload_direto).execute()
            return f"✅ Lançamento de **{descricao}** (R$ {valor:,.2f}) realizado com sucesso!"

    return "Ação concluída com sucesso!"


@st.dialog("🎙️ Conversar com o ORCAS")
def exibir_modal_voz_orcas(supabase, id_usuario, planos_disponiveis):
    """
    Modal de interface com fluxo em duas etapas: Gravação -> Checagem/Confirmação.
    """
    st.write("👋 **Olá! Em que posso ajudar nos seus lançamentos hoje?**")

    # Inicialização dos estados da sessão do modal
    if "etapa_voz" not in st.session_state:
        st.session_state.etapa_voz = "gravacao"
    if "dados_interpretados" not in st.session_state:
        st.session_state.dados_interpretados = None

    # ------------------------------------------------------------------
    # ETAPA 1: GRAVAÇÃO E TRANSCRIÇÃO
    # ------------------------------------------------------------------
    if st.session_state.etapa_voz == "gravacao":
        # Verificação de Limites Mensais
        pode_usar, uso_atual, limite_max = verificar_e_incrementar_limite(supabase, id_usuario)

        if not pode_usar:
            st.error(
                f"⚠️ **Você atingiu o limite mensal do recurso de voz!**\n\n"
                f"Você utilizou **{uso_atual}/{limite_max}** comandos neste mês.\n"
                f"Faça um upgrade de plano na tela de **Gestão / Configurações** para expandir seu limite."
            )
            return

        st.caption(f"📊 Uso do recurso de voz no mês: **{uso_atual}/{limite_max}** chamadas.")

        audio_input = st.audio_input("Grave seu comando abaixo:")

        if audio_input:
            with st.spinner("🤖 ORCAS está processando e interpretando seu áudio..."):
                try:
                    audio_bytes = audio_input.getvalue()
                    dados = processar_comando_voz(audio_bytes, planos_disponiveis)

                    # Se o plano for ambíguo, interrompe e avisa o usuário
                    if not dados.get("projeto_id") and len(planos_disponiveis) > 1 and dados.get("intencao") != "CONSULTAR":
                        st.warning(
                            f"🤖 **ORCAS:** {dados.get('resposta_orcas')}\n\n"
                            f"*Por favor, especifique qual dos seus planos usar ({', '.join(planos_disponiveis)}).*"
                        )
                        return

                    # Guarda o resultado e avança para a tela de confirmação
                    st.session_state.dados_interpretados = dados
                    st.session_state.etapa_voz = "confirmacao"
                    st.rerun()

                except Exception as e:
                    st.error(f"Não foi possível processar o áudio. Tente novamente. (Erro: {e})")

    # ------------------------------------------------------------------
    # ETAPA 2: EXIBIÇÃO DA TRANSCRIÇÃO E CONFIRMAÇÃO
    # ------------------------------------------------------------------
    elif st.session_state.etapa_voz == "confirmacao":
        dados = st.session_state.dados_interpretados or {}

        # Destaque com o que foi efetivamente ouvido
        st.info(f'🗣️ **Você disse:** "{dados.get("transcricao", "Áudio não transcrito")}"')

        # Card de resumo dos dados interpretados
        with st.container(border=True):
            st.subheader("📋 Resumo do Lançamento")
            st.write(f"🤖 **ORCAS:** {dados.get('resposta_orcas', '')}")
            st.markdown("---")

            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"• **Ação:** {dados.get('intencao', '-')}")
                st.write(f"• **Plano:** {dados.get('projeto_id') or 'Padrão'}")
                st.write(f"• **Descrição:** {dados.get('descricao', '-')}")
            with col_b:
                st.write(f"• **Tipo:** {dados.get('tipo', '-')}")
                valor_fmt = f"R$ {float(dados.get('valor') or 0.0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                st.write(f"• **Valor:** {valor_fmt}")
                st.write(f"• **Data:** {dados.get('data_vencimento', '-')}")

        st.markdown("---")
        btn_salvar, btn_refazer = st.columns(2)

        with btn_salvar:
            if st.button("✅ Confirmar e Gravar", type="primary", use_container_width=True):
                msg_sucesso = executar_acao_no_supabase(supabase, id_usuario, dados)
                st.success(msg_sucesso)
                
                # Reseta o modal para a próxima gravação
                st.session_state.etapa_voz = "gravacao"
                st.session_state.dados_interpretados = None
                st.rerun()

        with btn_refazer:
            if st.button("🔄 Falar Novamente", use_container_width=True):
                # Cancela e volta para a etapa de gravação
                st.session_state.etapa_voz = "gravacao"
                st.session_state.dados_interpretados = None
                st.rerun()