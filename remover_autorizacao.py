"""
Remove uma autorização de avaliação atrasada pelo ID.

1) Rode antes o consultar_autorizacoes.py pra descobrir o "id" que você quer remover.
2) Depois rode assim, na raiz do projeto (onde tem o .env):
    python remover_autorizacao.py 3
   (troque o "3" pelo id que você quer apagar)
"""
import sys
from sqlalchemy import text
from app.database import get_engine

if len(sys.argv) != 2:
    print("Uso: python remover_autorizacao.py <id>")
    sys.exit(1)

autorizacao_id = int(sys.argv[1])
engine = get_engine()

with engine.begin() as conn:
    resultado = conn.execute(
        text("DELETE FROM autorizacoes_avaliacao_atrasada WHERE id = :id RETURNING supervisor, mes_referencia;"),
        {"id": autorizacao_id},
    ).fetchone()

if resultado:
    print(f"Autorização removida: supervisor='{resultado.supervisor}', mes_referencia={resultado.mes_referencia}")
else:
    print(f"Nenhuma autorização encontrada com id={autorizacao_id}.")
