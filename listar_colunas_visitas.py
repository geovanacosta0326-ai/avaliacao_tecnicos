"""
Lista as colunas reais da tabela acompanhamento_mensal_visitas, pra
confirmar os nomes certos dos campos de projeto.

Rode assim, na raiz do projeto (onde tem o .env):
    python listar_colunas_visitas.py
"""
from sqlalchemy import text
from app.database import get_engine

engine = get_engine()

with engine.connect() as conn:
    rows = conn.execute(
        text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'acompanhamento_mensal_visitas'
            ORDER BY column_name;
        """)
    ).fetchall()

print(f"{len(rows)} coluna(s) encontrada(s) em acompanhamento_mensal_visitas:\n")
for r in rows:
    marca = " <<<" if "projeto" in r.column_name.lower() else ""
    print(f"  {r.column_name} ({r.data_type}){marca}")
