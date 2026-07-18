"""
Cria as tabelas novas no banco (usuarios_supervisores, avaliacoes_tecnicos)
usando a mesma conexão já configurada no .env — não precisa ter o psql
instalado.

USO:
    python criar_tabelas.py
"""
from sqlalchemy import text
from app.database import get_engine


def main():
    with open("sql/schema.sql", "r", encoding="utf-8") as f:
        sql = f.read()

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(sql))

    print("✔ Tabelas criadas/verificadas com sucesso: usuarios_supervisores, avaliacoes_tecnicos")


if __name__ == "__main__":
    main()
