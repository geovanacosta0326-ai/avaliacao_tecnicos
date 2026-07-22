"""
Acha em qual(is) tabela(s) do banco existem colunas com "projeto" ou
"atividade" no nome, e lista todas as colunas de cada uma (incluindo
o nome da coluna de id/técnico), pra confirmar de onde a tela
"Vínculos de técnicos" está puxando esses dados.

Rode assim, na raiz do projeto (onde tem o .env):
    python localizar_colunas_projeto_atividade.py
"""
from sqlalchemy import text
from app.database import get_engine

engine = get_engine()

with engine.connect() as conn:
    achadas = conn.execute(
        text("""
            SELECT DISTINCT table_schema, table_name
            FROM information_schema.columns
            WHERE column_name ILIKE '%projeto%' OR column_name ILIKE '%atividade%'
            ORDER BY table_schema, table_name;
        """)
    ).fetchall()

    print(f"{len(achadas)} tabela(s) com coluna 'projeto' ou 'atividade':\n")
    for schema, tabela in achadas:
        print(f"== {schema}.{tabela} ==")
        cols = conn.execute(
            text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :tabela
                ORDER BY ordinal_position;
            """),
            {"schema": schema, "tabela": tabela},
        ).fetchall()
        for c in cols:
            marca = " <<<" if ("projeto" in c.column_name.lower() or "atividade" in c.column_name.lower()) else ""
            print(f"   {c.column_name} ({c.data_type}){marca}")
        print()
