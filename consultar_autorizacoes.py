"""
Lista todas as autorizações de avaliação atrasada registradas no banco.

Rode assim, na raiz do projeto (onde tem o .env):
    python consultar_autorizacoes.py
"""
from sqlalchemy import text
from app.database import get_engine

engine = get_engine()

with engine.connect() as conn:
    rows = conn.execute(
        text("""
            SELECT id, supervisor, mes_referencia, autorizado_por, criado_em
            FROM autorizacoes_avaliacao_atrasada
            ORDER BY criado_em DESC;
        """)
    ).fetchall()

if not rows:
    print("Nenhuma autorização registrada no momento.")
else:
    print(f"{len(rows)} autorização(ões) encontrada(s):\n")
    for r in rows:
        print(
            f"id={r.id} | supervisor='{r.supervisor}' | mes_referencia={r.mes_referencia} "
            f"| autorizado_por='{r.autorizado_por}' | criado_em={r.criado_em}"
        )
