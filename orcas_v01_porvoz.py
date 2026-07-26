import streamlit as st
import google.generativeai as genai
from datetime import datetime, date
import json

# --- CONFIGURAÇÃO DA API DO GEMINI ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# Tabela de limites configuráveis
LIMITES_USO = {
    "PADRAO": 30,          # Ex: 30 interações de voz/mês
    "INTERMEDIARIO": 100,  # Ex: 100 interações de voz/mês
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

            # Incrementa o uso no Supabase (se as colunas existirem no seu banco)
            try:
                novo_uso = uso_atual + 1
                supabase.table("usuarios").update({"uso_voz_mes": novo_uso}).eq("id", usuario_id).execute()
            except Exception:
                pass # Evita travar caso a coluna uso_voz_mes ainda não tenha sido criada no Supabase
                
            return True, uso_atual + 1, limite_permitido
            
    except Exception as e:
        return True, 0, 30

    return True, 0, 30


def processar_comando_voz(audio_bytes, planos_disponiveis):
    """
    Envia o áudio ao Gemini e retorna o JSON exato mapeado para a tabela 'lancamentos'.
    """
    model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
    Você é o assistente financeiro de voz do aplicativo ORCAS.
    Data de hoje: {date.today()}
    Planos ativos cadastrados pelo usuário: {planos_disponiveis}

    Analise o áudio e responda EXCLUSIVAMENTE um objeto JSON válido (sem textos explicativos ou markdown):
    
    {{
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
        return f"✅ Lançamento **{descricao}** (R$ {valor:,.2f}) projetado com sucesso no plano **{projeto_id}**!"

    # 2. REALIZAR / CONCILIAR (UPDATE)
    elif intencao == "REALIZAR":
        # Procura lançamento pendente correspondente na tabela 'lancamentos'
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
            # Se não encontrou lançamento prévio, realiza um novo direto
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
            return f"✅ Lançamento direto de **{descricao}** (R$ {valor:,.2f}) realizado no plano **{projeto_id}**!"

    return "Ação concluída com sucesso!"


@st.dialog("🎙️ Conversar com o ORCAS")
def exibir_modal_voz_orcas(supabase, id_usuario, planos_disponiveis):
    """
    Modal de interface acionado pelo botão na barra lateral.
    """
    st.write("👋 **Olá! Em que posso ajudar nos seus lançamentos hoje?**")

    # Verificação de Limites
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
        st.info("🤖 **ORCAS:** Processando áudio via Gemini...")

        try:
            audio_bytes = audio_input.getvalue()
            dados = processar_comando_voz(audio_bytes, planos_disponiveis)

            # Validação de Ambiguidade de Plano
            if not dados.get("projeto_id") and len(planos_disponiveis) > 1 and dados.get("intencao") != "CONSULTAR":
                st.warning(f"🤖 **ORCAS:** {dados.get('resposta_orcas')}\n\n*Por favor, especifique qual dos seus planos usar ({', '.join(planos_disponiveis)}).*")
                return

            # Exibição do Card de Confirmação
            with st.container(border=True):
                st.subheader("📋 Resumo do Comando Entendido")
                st.write(f"🤖 **ORCAS:** {dados.get('resposta_orcas')}")
                st.markdown("---")
                
                col_a, col_b = st.columns(2)
                with col_a:
                    st.write(f"• **Ação:** {dados.get('intencao')}")
                    st.write(f"• **Plano:** {dados.get('projeto_id') or 'Não informado'}")
                    st.write(f"• **Descrição:** {dados.get('descricao')}")
                with col_b:
                    st.write(f"• **Tipo:** {dados.get('tipo')}")
                    st.write(f"• **Valor:** R$ {float(dados.get('valor') or 0.0):,.2f}")
                    st.write(f"• **Data:** {dados.get('data_vencimento')}")

                st.markdown("---")
                btn_salvar, btn_cancelar = st.columns(2)

                with btn_salvar:
                    if st.button("✅ Confirmar e Gravar", type="primary", use_container_width=True):
                        msg_sucesso = executar_acao_no_supabase(supabase, id_usuario, dados)
                        st.success(msg_sucesso)
                        st.rerun()

                with btn_cancelar:
                    if st.button("❌ Cancelar", use_container_width=True):
                        st.rerun()

        except Exception as e:
            st.error(f"Não foi possível processar o áudio. Tente novamente. (Erro: {e})")