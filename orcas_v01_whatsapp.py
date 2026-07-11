import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
import urllib.parse  # <-- Nativo: Para formatar o texto pro padrão de URL
import webbrowser    # <-- Nativo: Para abrir o WhatsApp no seu navegador de graça

# --- CONFIGURAÇÃO DA PÁGINA (FOCADO EM MOBILE) ---
st.set_page_config(page_title="Orcas Zap", page_icon="💬", layout="centered")

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; max-width: 450px; }
    .zap-header { background-color: #075E54; color: white; padding: 15px; border-radius: 10px 10px 0 0; font-weight: bold; margin-bottom: 15px; }
    .zap-card { background-color: #DCF8C6; padding: 12px; border-radius: 8px; margin-bottom: 10px; color: #303030; box-shadow: 1px 1px 2px rgba(0,0,0,0.1); }
    .zap-alert { background-color: #FFE699; padding: 12px; border-radius: 8px; margin-bottom: 15px; color: #5C4300; font-size: 13px; font-weight: 500; }
    </style>
""", unsafe_allow_html=True)


def disparar_whatsapp_gratuito(numero_celular, texto):
    """
    Usa a API pública e gratuita do WhatsApp para abrir o navegador
    já com a mensagem pronta para envio.
    """
    # Codifica o texto para o formato que a URL aceita (transforma espaços em %20, etc.)
    texto_codificado = urllib.parse.quote(texto)
    
    # Monta o link oficial gratuito do WhatsApp
    link_whatsapp = f"https://api.whatsapp.com/send?phone={numero_celular}&text={texto_codificado}"
    
    print(f"\n🌍 Opening WhatsApp Web/App para enviar para: {numero_celular}...")
    # Abre o navegador padrão do seu computador de forma automática
    webbrowser.open(link_whatsapp)
    return True


def enviar_mensagem_whatsapp_batch(supabase, id_usuario_teste=None, celular_teste=None):
    """
    Processa os lançamentos e monta o alerta de conciliação.
    """
    fuso = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje = datetime.now(fuso).date()
    limite_3_dias = hoje - timedelta(days=3)
    
    if id_usuario_teste and celular_teste:
        usuarios_lista = [{"id": id_usuario_teste, "nome": "Testador Orcas", "telefone": celular_teste}]
    else:
        # Busca usuários que ativaram o recurso de zap
        res_users = supabase.table("usuarios").select("id, nome, telefone").eq("zap_ativo", True).execute()
        usuarios_lista = res_users.data if res_users.data else []
    
    for user in usuarios_lista:
        uid = user["id"]
        celular = str(user["telefone"]).strip().replace("+", "").replace("-", "").replace(" ", "")
        
        # Busca os lançamentos pendentes
        lancamentos = supabase.table("lancamentos")\
            .select("id, data, valor, descricao")\
            .eq("usuario_id", uid)\
            .neq("status", "conciliado")\
            .lte("data", hoje.strftime('%Y-%m-%d'))\
            .execute()
            
        if not lancamentos.data:
            print(f"Nenhum lançamento pendente encontrado para {user['nome']}.")
            continue
            
        tem_anteriores_ao_limite = False
        for l in lancamentos.data:
            data_l = datetime.strptime(l["data"], "%Y-%m-%d").date()
            if data_l < limite_3_dias:
                tem_anteriores_ao_limite = True
                break
                
        # Montagem do corpo da mensagem
        texto_msg = f"Olá, {user['nome']}! 💬\n\nVocê tem lançamentos aguardando conciliação hoje.\n"
        
        if tem_anteriores_ao_limite:
            data_limite_fmt = limite_3_dias.strftime('%d/%m/%Y')
            texto_msg += f"\n⚠️ *Aviso:* Existem lançamentos ainda não conciliados antes de {data_limite_fmt}, faça essa conciliação utilizando seu aplicativo.\n"
            
        # IMPORTANTE: Altere para a URL real onde seu Streamlit está rodando na nuvem ou em localhost
        link_conciliacao = f"http://localhost:8501/orcas_v01_whatsapp?token={uid}"
        texto_msg += f"\n👉 Clique aqui para conciliar agora pelo celular:\n{link_conciliacao}"
        
        # Dispara usando o navegador (Método Gratuito)
        disparar_whatsapp_gratuito(celular, texto_msg)


def exibir_interface_mobile(supabase, uid_usuario):
    """
    Interface Streamlit renderizada no celular do usuário ao clicar no link
    """
    fuso = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje = datetime.now(fuso).date()
    limite_3_dias = hoje - timedelta(days=3)
    primeiro_dia_mes = hoje.replace(day=1)
    ultimo_dia_mes = (primeiro_dia_mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    st.markdown('<div class="zap-header">💬 Orcas Conciliação Rápida</div>', unsafe_allow_html=True)

    listar_tudo_mes = st.toggle("📅 Listar todos os Lançamentos do Mês")
    sem_planejamento = st.toggle("⚡ Lançar sem Planejamento")

    if sem_planejamento:
        st.subheader("Novo Lançamento Direto")
        desc_rapida = st.text_input("Descrição:")
        val_rapido = st.number_input("Valor (R$):", min_value=0.0, step=10.0)
        if st.button("Confirmar Lançamento", use_container_width=True, type="primary"):
            if desc_rapida:
                supabase.table("lancamentos").insert({
                    "usuario_id": uid_usuario,
                    "data": hoje.strftime('%Y-%m-%d'),
                    "descricao": desc_rapida,
                    "valor": float(val_rapido),
                    "status": "conciliado"
                }).execute()
                st.success("Lançado e conciliado!")
                st.rerun()

    if listar_tudo_mes:
        res_lanc = supabase.table("lancamentos").select("*")\
            .eq("usuario_id", uid_usuario)\
            .gte("data", primeiro_dia_mes.strftime('%Y-%m-%d'))\
            .lte("data", ultimo_dia_mes.strftime('%Y-%m-%d'))\
            .order("data")\
            .execute()
    else:
        res_lanc = supabase.table("lancamentos").select("*")\
            .eq("usuario_id", uid_usuario)\
            .neq("status", "conciliado")\
            .gte("data", limite_3_dias.strftime('%Y-%m-%d'))\
            .lte("data", hoje.strftime('%Y-%m-%d'))\
            .order("data")\
            .execute()

    res_antigos = supabase.table("lancamentos").select("id", count="exact")\
        .eq("usuario_id", uid_usuario)\
        .neq("status", "conciliado")\
        .lt("data", limite_3_dias.strftime('%Y-%m-%d'))\
        .execute()

    if res_antigos.count and res_antigos.count > 0:
        dt_limite_fmt = limite_3_dias.strftime('%d/%m/%Y')
        st.markdown(f'<div class="zap-alert">⚠️ Existem lançamentos ainda não conciliados antes de {dt_limite_fmt}, faça essa conciliação utilizando seu aplicativo.</div>', unsafe_allow_html=True)

    if not res_lanc.data:
        st.info("Nenhum lançamento pendente encontrado para este período.")
        return

    for item in res_lanc.data:
        id_lanc = item["id"]
        data_fmt = datetime.strptime(item["data"], "%Y-%m-%d").strftime("%d/%m")
        valor_original = float(item["valor"] or 0.0)
        status_atual = item.get("status")
        
        with st.container():
            st.markdown(
                f"""
                <div class="zap-card">
                    <b>{data_fmt} - {item['descricao']}</b><br>
                    Valor Previsto: R$ {valor_original:,.2f} { ' (✅ Conciliado)' if status_atual == 'conciliado' else ''}
                </div>
                """, 
                unsafe_allow_html=True
            )
            
            if status_atual != "conciliado":
                col_inp, col_btn = st.columns([2, 1])
                valor_informado = col_inp.text_input("Valor Pago:", placeholder=f"{valor_original:.2f}", key=f"val_{id_lanc}")
                
                if col_btn.button("Ok", key=f"btn_{id_lanc}", use_container_width=True):
                    valor_final_conciliacao = float(valor_informado) if valor_informado.strip() else valor_original
                    
                    supabase.table("lancamentos").update({
                        "status": "conciliado",
                        "valor_pago": valor_final_conciliacao,
                        "data_conciliacao": hoje.strftime('%Y-%m-%d')
                    }).eq("id", id_lanc).execute()
                    
                    st.toast("Conciliado com sucesso!")
                    st.rerun()
        st.write("---")

# --- CONTROLE DE EXECUÇÃO ---
if __name__ == "__main__":
    import sys
    # Importa a função correta do seu arquivo de segurança real
    from orcas_v01_security import init_connection
    
    # Inicializa o contexto do Supabase chamando a função
    supabase_ctx = init_connection()
    
    if len(sys.argv) > 1:
        comando = sys.argv[1]
        
        if comando == "batch":
            enviar_mensagem_whatsapp_batch(supabase_ctx)
            
        elif comando == "teste":
            # 🧪 CONFIGURAÇÃO DO SEU TESTE MANUAL GRATUITO:
            MEU_ID_USUARIO = 1 
            MEU_CELULAR = "5511972810372"  
            
            print("⚙️ Iniciando teste gratuito de notificação...")
            enviar_mensagem_whatsapp_batch(supabase_ctx, id_usuario_teste=MEU_ID_USUARIO, celular_teste=MEU_CELULAR)
    else:
        query_params = st.query_params
        token_usuario = query_params.get("token")
        
        if token_usuario:
            exibir_interface_mobile(supabase_ctx, token_usuario)
        else:
            st.warning("Acesso restrito. Utilize o link enviado para o seu WhatsApp.")