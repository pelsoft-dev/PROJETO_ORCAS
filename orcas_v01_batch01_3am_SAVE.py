import os
from supabase import create_client
from datetime import datetime, timedelta, timezone

# Configurações de Ambiente
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

def job_madrugada():
    if not URL or not KEY:
        print("ERRO: VARIÁVEIS DE AMBIENTE (SUPABASE) NÃO ENCONTRADAS.")
        return

    supabase = create_client(URL, KEY)
    
    # Configuração de fuso horário (Jundiaí/Brasília)
    fuso_br = timezone(timedelta(hours=-3))
    agora = datetime.now(fuso_br)
    hoje = agora.date()
    ontem = hoje - timedelta(days=1)
    
    print(f"--- INICIANDO ROTINA ORCAS (BATCH 3AM): {hoje.strftime('%d/%m/%Y')} ---")

    try:
        # --- 1. PROCESSAR MÉDIA HISTÓRICA TOTAL ---
        # Busca todos os lançamentos de hoje para frente que usam média
        proximos = supabase.table("lancamentos")\
            .select("id, descricao, usuario_id")\
            .eq("usar_media", True)\
            .gte("data", hoje.strftime('%Y-%m-%d'))\
            .execute()

        if proximos.data:
            # Identifica combinações únicas de Descrição + Usuário para não repetir cálculo
            descricoes_unicas = set((x['descricao'], x['usuario_id']) for x in proximos.data)

            for desc, user_id in descricoes_unicas:
                # Busca TODO o histórico de realizados desta descrição para este usuário
                historico = supabase.table("lancamentos")\
                    .select("valor_real")\
                    .eq("descricao", desc)\
                    .eq("usuario_id", user_id)\
                    .eq("status", "Realizado")\
                    .lt("data", hoje.strftime('%Y-%m-%d'))\
                    .execute()
                
                if historico.data:
                    valores = [h['valor_real'] for h in historico.data if h['valor_real'] > 0]
                    if valores:
                        media_total = sum(valores) / len(valores)
                        
                        # Atualiza todos os planos futuros com a nova média
                        supabase.table("lancamentos")\
                            .update({"valor_plan": round(float(media_total), 2)})\
                            .eq("descricao", desc)\
                            .eq("usuario_id", user_id)\
                            .eq("usar_media", True)\
                            .eq("status", "Planejado")\
                            .gte("data", hoje.strftime('%Y-%m-%d'))\
                            .execute()
                        print(f"MÉDIA HISTÓRICA ATUALIZADA: {desc} -> R$ {media_total:.2f}")

        # --- 2. PROCESSAR RESÍDUOS (Regras de Virada/Vencimento) ---
        # Busca lançamentos de ontem que não foram totalmente realizados
        residuos = supabase.table("lancamentos")\
            .select("*")\
            .eq("data", ontem.strftime('%Y-%m-%d'))\
            .eq("status", "Planejado")\
            .neq("regra_parcial", "Zera o Realizado")\
            .execute()

        for item in residuos.data:
            valor_p = float(item.get('valor_plan', 0))
            valor_r = float(item.get('valor_real', 0))
            sobra = valor_p - valor_r
            
            if sobra > 0:
                regra = item['regra_parcial']
                
                # Localiza se existe o mesmo lançamento no futuro para aplicar a sobra
                proximo = supabase.table("lancamentos")\
                    .select("id, valor_plan")\
                    .eq("descricao", item['descricao'])\
                    .eq("usuario_id", item['usuario_id'])\
                    .gt("data", ontem.strftime('%Y-%m-%d'))\
                    .order("data")\
                    .limit(1)\
                    .execute()

                # REGRA: ADICIONAR (Soma a sobra ao valor já planejado do mês seguinte)
                if "Adicione a diferença" in regra:
                    if proximo.data:
                        novo_v = float(proximo.data[0]['valor_plan']) + sobra
                        supabase.table("lancamentos")\
                            .update({"valor_plan": round(novo_v, 2)}).eq("id", proximo.data[0]['id']).execute()
                        print(f"RESÍDUO ADICIONADO: {item['descricao']} (+ R$ {sobra:.2f})")

                # REGRA: COPIAR (Substitui o valor do próximo ou cria um novo se não existir)
                elif "Copia a diferença" in regra:
                    if proximo.data:
                        # Substituição inteligente (ideal para orçamentos de projetos/reformas)
                        supabase.table("lancamentos")\
                            .update({"valor_plan": round(sobra, 2)}).eq("id", proximo.data[0]['id']).execute()
                        print(f"RESÍDUO COPIADO (Substituição): {item['descricao']} (R$ {sobra:.2f} transferido)")
                    else:
                        # Criação (se não houver plano futuro, ele cria para hoje)
                        novo_item = item.copy()
                        novo_item.pop('id', None)
                        novo_item['data'] = hoje.strftime('%Y-%m-%d')
                        novo_item['valor_plan'] = round(sobra, 2)
                        novo_item['valor_real'] = 0.0
                        supabase.table("lancamentos").insert(novo_item).execute()
                        print(f"RESÍDUO COPIADO (Criação): {item['descricao']} (R$ {sobra:.2f} criado para hoje)")

    except Exception as e:
        print(f"ERRO DURANTE A EXECUÇÃO: {e}")

    print(f"--- ROTINA FINALIZADA ÀS {datetime.now(fuso_br).strftime('%H:%M:%S')} ---")

if __name__ == "__main__":
    job_madrugada()