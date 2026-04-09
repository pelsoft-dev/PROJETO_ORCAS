import os
from supabase import create_client
from datetime import datetime, timedelta, timezone

URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

def job_madrugada():
    if not URL or not KEY:
        print("ERRO: VARIÁVEIS DE AMBIENTE NÃO ENCONTRADAS.")
        return

    supabase = create_client(URL, KEY)
    fuso_br = timezone(timedelta(hours=-3))
    hoje = datetime.now(fuso_br).date()
    ontem = hoje - timedelta(days=1)
    
    print(f"--- INICIANDO ROTINA ORCAS (BATCH 3AM): {hoje.strftime('%d/%m/%Y')} ---")

    try:
        # --- 1. MÉDIA HISTÓRICA TOTAL ---
        proximos = supabase.table("lancamentos")\
            .select("id, descricao, usuario_id")\
            .eq("usar_media", True)\
            .gte("data", hoje.strftime('%Y-%m-%d'))\
            .execute()

        if proximos.data:
            descricoes_unicas = set((x['descricao'], x['usuario_id']) for x in proximos.data)

            for desc, user_id in descricoes_unicas:
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
                        supabase.table("lancamentos")\
                            .update({"valor_plan": round(float(media_total), 2)})\
                            .eq("descricao", desc)\
                            .eq("usuario_id", user_id)\
                            .eq("usar_media", True)\
                            .eq("status", "Planejado")\
                            .gte("data", hoje.strftime('%Y-%m-%d'))\
                            .execute()
                        print(f"MÉDIA HISTÓRICA: {desc} -> R$ {media_total:.2f}")

        # --- 2. PROCESSAR RESÍDUOS ---
        residuos = supabase.table("lancamentos")\
            .select("*")\
            .eq("data", ontem.strftime('%Y-%m-%d'))\
            .eq("status", "Planejado")\
            .neq("regra_parcial", "Zera o Realizado")\
            .execute()

        for item in residuos.data:
            sobra = float(item.get('valor_plan', 0)) - float(item.get('valor_real', 0))
            if sobra <= 0: continue

            regra = item['regra_parcial']
            
            # Busca se existe um próximo lançamento planejado
            proximo = supabase.table("lancamentos")\
                .select("id, valor_plan")\
                .eq("descricao", item['descricao'])\
                .eq("usuario_id", item['usuario_id'])\
                .gt("data", ontem.strftime('%Y-%m-%d'))\
                .order("data")\
                .limit(1)\
                .execute()

            # REGRA: ADICIONAR (Soma)
            if "Adicione a diferença" in regra:
                if proximo.data:
                    novo_v = float(proximo.data[0]['valor_plan']) + sobra
                    supabase.table("lancamentos").update({"valor_plan": round(novo_v, 2)}).eq("id", proximo.data[0]['id']).execute()
                    print(f"SOMA: {item['descricao']} (+ R$ {sobra:.2f})")

            # REGRA: COPIAR (Substitui ou Cria)
            elif "Copia a diferença" in regra:
                if proximo.data:
                    # Se existe, apenas substitui o valor planejado pela sobra
                    supabase.table("lancamentos").update({"valor_plan": round(sobra, 2)}).eq("id", proximo.data[0]['id']).execute()
                    print(f"COPIA (Substituição): {item['descricao']} (Valor R$ {sobra:.2f} transferido)")
                else:
                    # Se não existe, cria um novo para hoje
                    novo_item = item.copy()
                    novo_item.pop('id', None)
                    novo_item['data'] = hoje.strftime('%Y-%m-%d')
                    novo_item['valor_plan'] = round(sobra, 2)
                    novo_item['valor_real'] = 0.0
                    supabase.table("lancamentos").insert(novo_item).execute()
                    print(f"COPIA (Criação): {item['descricao']} (R$ {sobra:.2f} criado para hoje)")

    except Exception as e:
        print(f"ERRO: {e}")

    print(f"--- FIM DA ROTINA ---")

if __name__ == "__main__":
    job_madrugada()