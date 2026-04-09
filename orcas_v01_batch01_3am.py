import os
from supabase import create_client
from datetime import datetime, timedelta, timezone

# Configurações de Conexão - Buscando das variáveis de ambiente do sistema
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

def job_madrugada():
    if not URL or not KEY:
        print("ERRO: VARIÁVEIS DE AMBIENTE SUPABASE_URL OU SUPABASE_KEY NÃO ENCONTRADAS.")
        return

    supabase = create_client(URL, KEY)
    
    # Ajuste de Fuso Horário para Jundiaí/Brasília (UTC-3)
    fuso_br = timezone(timedelta(hours=-3))
    hoje = datetime.now(fuso_br).date()
    ontem = hoje - timedelta(days=1)
    
    print(f"--- INICIANDO ROTINA ORCAS (BATCH 3AM): {hoje.strftime('%d/%m/%Y')} ---")

    # --- 1. PROCESSAR MÉDIA DOS REALIZADOS ---
    # Busca lançamentos futuros que possuem a flag 'usar_media' ativa
    try:
        proximos = supabase.table("lancamentos")\
            .select("id, descricao, usuario_id, projeto_id")\
            .eq("usar_media", True)\
            .gte("data", hoje.strftime('%Y-%m-%d'))\
            .execute()

        if proximos.data:
            # Identifica combinações únicas de descrição e usuário para não repetir cálculos
            descricoes_unicas = set((x['descricao'], x['usuario_id']) for x in proximos.data)

            for desc, user_id in descricoes_unicas:
                # Busca o histórico dos últimos 3 lançamentos já 'Realizados'
                historico = supabase.table("lancamentos")\
                    .select("valor_real")\
                    .eq("descricao", desc)\
                    .eq("usuario_id", user_id)\
                    .eq("status", "Realizado")\
                    .lt("data", hoje.strftime('%Y-%m-%d'))\
                    .order("data", desc=True)\
                    .limit(3)\
                    .execute()
                
                if historico.data:
                    valores = [h['valor_real'] for h in historico.data if h['valor_real'] > 0]
                    if valores:
                        media_calculada = sum(valores) / len(valores)
                        
                        # Atualiza todos os lançamentos 'Planejados' futuros com o novo valor médio
                        supabase.table("lancamentos")\
                            .update({"valor_plan": round(float(media_calculada), 2)})\
                            .eq("descricao", desc)\
                            .eq("usuario_id", user_id)\
                            .eq("usar_media", True)\
                            .eq("status", "Planejado")\
                            .gte("data", hoje.strftime('%Y-%m-%d'))\
                            .execute()
                        print(f"MÉDIA ATUALIZADA: {desc} -> R$ {media_calculada:.2f}")

        # --- 2. PROCESSAR RESÍDUOS (REGRAS PARCIAIS DE ONTEM) ---
        # Verifica quem não foi realizado ontem e possui regra de sobra
        residuos = supabase.table("lancamentos")\
            .select("*")\
            .eq("data", ontem.strftime('%Y-%m-%d'))\
            .eq("status", "Planejado")\
            .neq("regra_parcial", "Zera o Realizado")\
            .execute()

        for item in residuos.data:
            v_p = item.get('valor_plan', 0)
            v_r = item.get('valor_real', 0)
            sobra = v_p - v_r
            
            if sobra > 0:
                regra = item['regra_parcial']
                
                # REGRA: Adicionar a diferença no próximo lançamento existente
                if "Adicione a diferença" in regra:
                    proximo = supabase.table("lancamentos")\
                        .select("id, valor_plan")\
                        .eq("descricao", item['descricao'])\
                        .eq("usuario_id", item['usuario_id'])\
                        .gt("data", ontem.strftime('%Y-%m-%d'))\
                        .order("data")\
                        .limit(1)\
                        .execute()
                    
                    if proximo.data:
                        novo_v = float(proximo.data[0]['valor_plan']) + float(sobra)
                        supabase.table("lancamentos")\
                            .update({"valor_plan": round(novo_v, 2)})\
                            .eq("id", proximo.data[0]['id'])\
                            .execute()
                        print(f"RESÍDUO ADICIONADO: {item['descricao']} (+ R$ {sobra:.2f})")

                # REGRA: Copiar a diferença (cria um novo lançamento isolado)
                elif "Copia a diferença" in regra:
                    novo_item = item.copy()
                    novo_item.pop('id', None) # Remove o ID antigo para o Supabase gerar um novo
                    novo_item['data'] = hoje.strftime('%Y-%m-%d')
                    novo_item['valor_plan'] = round(float(sobra), 2)
                    novo_item['valor_real'] = 0.0
                    supabase.table("lancamentos").insert(novo_item).execute()
                    print(f"RESÍDUO COPIADO: {item['descricao']} (R$ {sobra:.2f}) criado para hoje.")

    except Exception as e:
        print(f"ERRO DURANTE A EXECUÇÃO: {e}")

    print(f"--- ROTINA FINALIZADA ÀS {datetime.now(fuso_br).strftime('%H:%M:%S')} ---")

if __name__ == "__main__":
    job_madrugada()