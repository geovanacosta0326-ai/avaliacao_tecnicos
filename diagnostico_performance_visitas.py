"""
Diagnostico de performance da base de visitas (acompanhamento_mensal_visitas).

Mostra:
  - quantas linhas tem a tabela
  - quantos técnicos distintos
  - quais índices já existem nela
  - quanto tempo a consulta pesada (a mesma usada na tela de Supervisores
    e na tela de cada técnico) leva pra rodar sozinha

Rode assim, na raiz do projeto (onde tem o .env):
    python diagnostico_performance_visitas.py
"""
import time
from sqlalchemy import text
from app.database import get_engine

engine = get_engine()

with engine.connect() as conn:
    total_linhas = conn.execute(
        text("SELECT COUNT(*) FROM acompanhamento_mensal_visitas;")
    ).scalar()
    total_tecnicos = conn.execute(
        text("SELECT COUNT(DISTINCT tecnico_responsavel) FROM acompanhamento_mensal_visitas;")
    ).scalar()

    print(f"Total de linhas em acompanhamento_mensal_visitas: {total_linhas}")
    print(f"Total de técnicos distintos: {total_tecnicos}\n")

    print("Índices existentes na tabela:")
    indices = conn.execute(
        text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'acompanhamento_mensal_visitas';
        """)
    ).fetchall()
    if not indices:
        print("  -> NENHUM índice encontrado nessa tabela (isso é ruim pra performance).")
    for i in indices:
        print(f"  - {i.indexname}: {i.indexdef}")

    print("\nRodando a consulta pesada (a mesma usada nas telas de técnico/supervisor)...")
    inicio = time.time()
    conn.execute(
        text("""
            WITH visitas AS (
                SELECT
                    tecnico_responsavel AS tecnico,
                    dt_visita_v::date AS dt_visita_v,
                    projeto,
                    FIRST_VALUE(projeto) OVER (
                        PARTITION BY tecnico_responsavel ORDER BY dt_visita_v::date DESC
                    ) AS projeto_atual,
                    FIRST_VALUE(atividade) OVER (
                        PARTITION BY tecnico_responsavel ORDER BY dt_visita_v::date DESC
                    ) AS atividade_atual,
                    FIRST_VALUE(supervisor_atual) OVER (
                        PARTITION BY tecnico_responsavel ORDER BY dt_visita_v::date DESC
                    ) AS supervisor_mais_recente,
                    MAX(dt_visita_v::date) OVER (PARTITION BY tecnico_responsavel) AS ultima_visita
                FROM public.acompanhamento_mensal_visitas
                WHERE tecnico_responsavel IS NOT NULL
            )
            SELECT DISTINCT ON (tecnico)
                tecnico,
                MIN(dt_visita_v) FILTER (WHERE projeto IS NOT DISTINCT FROM projeto_atual)
                    OVER (PARTITION BY tecnico) AS primeira_visita,
                ultima_visita,
                projeto_atual AS projeto_consolidado,
                atividade_atual AS atividade,
                supervisor_mais_recente AS supervisor_atual
            FROM visitas
            ORDER BY tecnico, dt_visita_v DESC;
        """)
    ).fetchall()
    duracao = time.time() - inicio
    print(f"Duração: {duracao:.2f} segundos")

    if duracao > 3:
        print("\n>>> Essa consulta sozinha já é lenta. O próximo passo seria criar um")
        print(">>> índice em acompanhamento_mensal_visitas(tecnico_responsavel, dt_visita_v).")
