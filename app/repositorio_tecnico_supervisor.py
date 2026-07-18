"""
Consultas e ações do vínculo Supervisor ↔ Técnico (manual, com histórico).

Diferente de repositorio.listar_tecnicos_do_supervisor (que hoje deduz o
supervisor automaticamente pela visita mais recente), aqui o vínculo é
mantido manualmente pelo próprio supervisor — ver seção 4 do descritivo.

IMPORTANTE: este módulo é ADITIVO por enquanto. A avaliação mensal ainda
usa repositorio.listar_tecnicos_do_supervisor (automático). A troca para
usar este vínculo manual na avaliação é uma decisão separada, combinada
à parte, para não quebrar o fluxo de avaliação de uma hora para outra.
"""
from sqlalchemy import text
from app.database import get_engine

# Todo técnico com pelo menos uma visita registrada, com primeira/última
# visita — igual ao usado na tela de técnico-empresa, mas sem depender
# daquele módulo (evita import cruzado).
QUERY_TODOS_TECNICOS_COM_VISITAS = """
SELECT
    tecnico_responsavel AS tecnico,
    MIN(dt_visita)       AS primeira_visita,
    MAX(dt_visita)       AS ultima_visita
FROM public.acompanhamento_mensal_visitas
WHERE tecnico_responsavel IS NOT NULL
GROUP BY tecnico_responsavel
ORDER BY tecnico_responsavel
"""


def listar_todos_tecnicos_com_visitas():
    """Todo técnico com visita registrada + primeira/última visita."""
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(text(QUERY_TODOS_TECNICOS_COM_VISITAS)).mappings().all()
    return [dict(l) for l in linhas]


def listar_todos_vinculos_do_supervisor(supervisor: str):
    """
    TODOS os vínculos deste supervisor — ativos e encerrados — para a
    tela "Técnicos da equipe" mostrar o histórico completo (com motivo e
    data de cada desvínculo), não só quem está ativo agora.
    """
    engine = get_engine()
    query = f"""
        SELECT
            ts.id AS vinculo_id, ts.tecnico, ts.mes_inicio, ts.mes_fim,
            ts.motivo_desvinculo,
            v.primeira_visita, v.ultima_visita
        FROM tecnico_supervisor ts
        LEFT JOIN ({QUERY_TODOS_TECNICOS_COM_VISITAS}) v ON v.tecnico = ts.tecnico
        WHERE ts.supervisor = :supervisor
        ORDER BY (ts.mes_fim IS NULL) DESC, ts.tecnico, ts.mes_inicio DESC;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query), {"supervisor": supervisor}).mappings().all()
    return [dict(l) for l in linhas]


def listar_vinculos_ativos_do_supervisor(supervisor: str):
    """
    Técnicos ATIVOS na equipe deste supervisor agora, com primeira/última
    visita (LEFT JOIN — o técnico aparece mesmo sem visita ainda).
    """
    engine = get_engine()
    query = f"""
        SELECT
            ts.id            AS vinculo_id,
            ts.tecnico,
            ts.mes_inicio,
            v.primeira_visita,
            v.ultima_visita
        FROM tecnico_supervisor ts
        LEFT JOIN ({QUERY_TODOS_TECNICOS_COM_VISITAS}) v ON v.tecnico = ts.tecnico
        WHERE ts.supervisor = :supervisor
          AND ts.mes_fim IS NULL
        ORDER BY ts.tecnico;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query), {"supervisor": supervisor}).mappings().all()
    return [dict(l) for l in linhas]


def listar_tecnicos_disponiveis(supervisor: str):
    """
    Todos os técnicos com visita registrada que NÃO estão hoje vinculados
    a este supervisor (podem já estar vinculados a outro supervisor —
    nesse caso o supervisor atual aparece, informativamente).
    """
    engine = get_engine()
    query = f"""
        SELECT
            v.tecnico,
            v.primeira_visita,
            v.ultima_visita,
            ts_outro.supervisor AS supervisor_atual_de_outro
        FROM ({QUERY_TODOS_TECNICOS_COM_VISITAS}) v
        LEFT JOIN tecnico_supervisor ts_outro
            ON ts_outro.tecnico = v.tecnico AND ts_outro.mes_fim IS NULL
        WHERE v.tecnico NOT IN (
            SELECT tecnico FROM tecnico_supervisor
            WHERE supervisor = :supervisor AND mes_fim IS NULL
        )
        ORDER BY v.tecnico;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query), {"supervisor": supervisor}).mappings().all()
    return [dict(l) for l in linhas]


def historico_vinculo_tecnico(tecnico: str):
    """Histórico completo (ativos e encerrados) de supervisores de um técnico."""
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(
            text("""
                SELECT id, supervisor, mes_inicio, mes_fim, motivo_desvinculo, criado_por
                FROM tecnico_supervisor
                WHERE tecnico = :tecnico
                ORDER BY mes_inicio DESC;
            """),
            {"tecnico": tecnico},
        ).mappings().all()
    return [dict(l) for l in linhas]


def listar_todos_vinculos_ativos():
    """Auditoria do coordenador: todos os vínculos ativos, de todos os supervisores."""
    engine = get_engine()
    query = f"""
        SELECT
            ts.id AS vinculo_id, ts.supervisor, ts.tecnico, ts.mes_inicio,
            v.primeira_visita, v.ultima_visita
        FROM tecnico_supervisor ts
        LEFT JOIN ({QUERY_TODOS_TECNICOS_COM_VISITAS}) v ON v.tecnico = ts.tecnico
        WHERE ts.mes_fim IS NULL
        ORDER BY ts.supervisor, ts.tecnico;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query)).mappings().all()
    return [dict(l) for l in linhas]


def vincular(tecnico: str, supervisor: str, mes_inicio, criado_por: str):
    """
    Cria um novo vínculo ativo supervisor-técnico.
    Se o técnico já tiver um vínculo ativo (com este ou outro supervisor),
    o índice único uq_tecnico_supervisor_ativo impede duplicidade — nesse
    caso é preciso desvincular o vínculo atual primeiro.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO tecnico_supervisor
                    (tecnico, supervisor, mes_inicio, criado_por)
                VALUES
                    (:tecnico, :supervisor, :mes_inicio, :criado_por)
            """),
            {
                "tecnico": tecnico,
                "supervisor": supervisor,
                "mes_inicio": mes_inicio,
                "criado_por": criado_por,
            },
        )


def desvincular(vinculo_id: int, mes_fim, motivo: str):
    """Encerra o vínculo (nunca apaga) — grava mes_fim e motivo."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE tecnico_supervisor
                SET mes_fim = :mes_fim,
                    motivo_desvinculo = :motivo,
                    atualizado_em = NOW()
                WHERE id = :id
            """),
            {"id": vinculo_id, "mes_fim": mes_fim, "motivo": motivo},
        )
