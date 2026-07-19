"""
Diagnostica por que um técnico não aparece na lista "Complementar cadastro"
de um supervisor específico.

Rode assim, na raiz do projeto (onde tem o .env):
    python diagnosticar_tecnico.py "NOME DO TECNICO" "NOME DO SUPERVISOR"
"""
import sys
from sqlalchemy import text
from app.database import get_engine
from app.repositorio import normalizar

if len(sys.argv) != 3:
    print('Uso: python diagnosticar_tecnico.py "NOME DO TECNICO" "NOME DO SUPERVISOR"')
    sys.exit(1)

tecnico_busca = sys.argv[1]
supervisor_busca = sys.argv[2]
alvo = normalizar(tecnico_busca)

engine = get_engine()

with engine.connect() as conn:
    # 1) Última visita registrada e quem é o supervisor_atual dela
    rows = conn.execute(
        text("""
            SELECT tecnico_responsavel, supervisor_atual, dt_visita, projeto_consolidado, atividade
            FROM acompanhamento_mensal_visitas
            ORDER BY dt_visita DESC;
        """)
    ).fetchall()

    ultima_visita = None
    for r in rows:
        if normalizar(r.tecnico_responsavel) == alvo:
            ultima_visita = r
            break

    print("=" * 60)
    if ultima_visita is None:
        print(f"Não encontrei NENHUMA visita para um técnico parecido com '{tecnico_busca}'.")
    else:
        print(f"Última visita encontrada:")
        print(f"  Técnico (como está gravado): {ultima_visita.tecnico_responsavel}")
        print(f"  Supervisor_atual dessa visita: {ultima_visita.supervisor_atual}")
        print(f"  Data da visita: {ultima_visita.dt_visita}")
        print(f"  Projeto: {ultima_visita.projeto_consolidado} | Atividade: {ultima_visita.atividade}")

        if ultima_visita.dt_visita.year < 2026:
            print(f"  ⚠️ Essa visita é de {ultima_visita.dt_visita.year} — por isso NÃO aparece mais na")
            print(f"     lista 'Complementar cadastro' (só mostra quem visitou em 2026+).")

        if normalizar(ultima_visita.supervisor_atual or "") != normalizar(supervisor_busca):
            print(f"  ⚠️ O supervisor_atual dessa visita ('{ultima_visita.supervisor_atual}') é DIFERENTE")
            print(f"     do supervisor que você está checando ('{supervisor_busca}') — por isso não")
            print(f"     aparece na lista dele. A visita mais recente aponta outra pessoa.")

    print("=" * 60)

    # 2) Vínculos (ativos e encerrados) desse técnico
    rows2 = conn.execute(
        text("SELECT * FROM vinculo_tecnico ORDER BY data_inicio DESC;")
    ).mappings().all()
    vinculos = [dict(r) for r in rows2 if normalizar(r["tecnico"]) == alvo]

    if not vinculos:
        print("Nenhum vínculo (ativo ou encerrado) encontrado para esse técnico.")
    else:
        print(f"{len(vinculos)} vínculo(s) encontrado(s):")
        for v in vinculos:
            status = "ATIVO" if v["data_desvinculacao"] is None else f"ENCERRADO em {v['data_desvinculacao']}"
            print(f"  - supervisor='{v['supervisor']}' | status={status} | motivo={v.get('motivo_desvinculacao')}")
