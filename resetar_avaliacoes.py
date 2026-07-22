"""
Faz um backup rapido (CSV) e depois apaga TODOS os dados das tabelas
relacionadas a avaliacao, para testar o sistema do zero.

Tabelas afetadas:
  - avaliacoes_tecnicos
  - configuracao_prazo_avaliacao   (volta pro padrao: dia_limite = 23)
  - prazos_avaliacao_mes
  - autorizacoes_avaliacao_atrasada
  - solicitacoes_prazo_avaliacao

NAO mexe em: vinculo_tecnico, usuarios_supervisores, acompanhamento_mensal_visitas.

Rode assim, na raiz do projeto (onde tem o .env):
    python resetar_avaliacoes.py

Ele pede uma confirmacao antes de apagar de verdade.
"""
import csv
import os
from datetime import datetime
from sqlalchemy import text
from app.database import get_engine

TABELAS = [
    "avaliacoes_tecnicos",
    "configuracao_prazo_avaliacao",
    "prazos_avaliacao_mes",
    "autorizacoes_avaliacao_atrasada",
    "solicitacoes_prazo_avaliacao",
]

engine = get_engine()
pasta_backup = f"backup_avaliacoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
os.makedirs(pasta_backup, exist_ok=True)

print("Fazendo backup em CSV antes de apagar...\n")
with engine.connect() as conn:
    for tabela in TABELAS:
        try:
            rows = conn.execute(text(f"SELECT * FROM {tabela};")).mappings().all()
        except Exception as e:
            print(f"  {tabela}: não existe ou deu erro ao ler ({e}) — pulando.")
            continue

        caminho = os.path.join(pasta_backup, f"{tabela}.csv")
        if rows:
            with open(caminho, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                for r in rows:
                    writer.writerow(dict(r))
        else:
            open(caminho, "w").close()
        print(f"  {tabela}: {len(rows)} linha(s) salva(s) em {caminho}")

print(f"\nBackup salvo na pasta: {pasta_backup}\n")

resposta = input(
    "Isso vai APAGAR PERMANENTEMENTE todos os dados das tabelas acima "
    "(o backup em CSV já foi feito). Digite APAGAR para confirmar: "
)

if resposta.strip().upper() != "APAGAR":
    print("Cancelado — nada foi apagado.")
    raise SystemExit(0)

with engine.begin() as conn:
    for tabela in TABELAS:
        try:
            conn.execute(text(f"TRUNCATE TABLE {tabela} RESTART IDENTITY CASCADE;"))
            print(f"  {tabela}: apagada.")
        except Exception as e:
            print(f"  {tabela}: não existe ou deu erro ({e}) — pulando.")

    # Recoloca a configuração padrão do prazo (dia 23), pra não quebrar nada
    conn.execute(
        text("""
            INSERT INTO configuracao_prazo_avaliacao (id, dia_limite)
            VALUES (1, 23)
            ON CONFLICT (id) DO NOTHING;
        """)
    )

print("\nPronto! Todas as tabelas de avaliação foram zeradas e o dia-limite padrão (23) foi restaurado.")
