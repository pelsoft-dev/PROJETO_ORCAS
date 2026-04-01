import sqlite3
conn = sqlite3.connect('orcas_saas.db')
try:
    conn.execute("ALTER TABLE usuarios ADD COLUMN zap_ativo INTEGER DEFAULT 0")
    conn.execute("ALTER TABLE usuarios ADD COLUMN telefone TEXT")
    conn.commit()
    print("Banco de dados atualizado com sucesso!")
except:
    print("Colunas já existem ou erro ao atualizar.")
conn.close()