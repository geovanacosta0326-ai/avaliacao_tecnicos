"""
Consulta consolidada: técnicos que já têm ao menos uma visita registrada,
com primeira/última visita (vindas de acompanhamento_mensal_visitas) e o
vínculo de empresa ATIVO no momento (vindo de tecnico_empresa, se existir).

Técnico sem nenhuma linha em tecnico_empresa ainda aparece na lista —
só com os campos de empresa em branco (LEFT JOIN), esperando o
coordenador completar.
"""

QUERY_TECNICOS_CONSOLIDADO = """
SELECT
    v.tecnico,
    v.primeira_visita,
    v.ultima_visita,
    e.id                  AS vinculo_id,
    e.empresa,
    e.cnpj_empresa,
    e.cpf,
    e.data_inicio,
    e.data_fim,
    e.motivo_desvinculo,
    CASE WHEN e.data_fim IS NULL AND e.id IS NOT NULL
         THEN TRUE ELSE FALSE END AS ativo
FROM (
    SELECT
        tecnico_responsavel AS tecnico,
        MIN(dt_visita)      AS primeira_visita,
        MAX(dt_visita)      AS ultima_visita
    FROM public.acompanhamento_mensal_visitas
    WHERE tecnico_responsavel IS NOT NULL
    GROUP BY tecnico_responsavel
) v
LEFT JOIN tecnico_empresa e
    ON e.tecnico = v.tecnico
    AND e.data_fim IS NULL   -- pega só o vínculo ativo atual, se houver
ORDER BY v.tecnico;
"""

# Histórico completo de vínculos de um técnico específico (para a tela de detalhe)
QUERY_HISTORICO_TECNICO_EMPRESA = """
SELECT empresa, cnpj_empresa, cpf, data_inicio, data_fim, motivo_desvinculo, criado_por
FROM tecnico_empresa
WHERE tecnico = :tecnico
ORDER BY data_inicio DESC;
"""

# Vínculo de empresa ATIVO (empresa + CPF) de uma lista de técnicos —
# usado para mostrar essa informação também na tela "Meus Técnicos" do
# supervisor, sem precisar de N consultas (uma por técnico).
QUERY_VINCULOS_ATIVOS_POR_TECNICOS = """
SELECT tecnico, empresa, cnpj_empresa, cpf, data_inicio
FROM tecnico_empresa
WHERE data_fim IS NULL
  AND tecnico = ANY(:tecnicos);
"""

from sqlalchemy import text
from app.database import get_engine


def listar_tecnicos_empresa():
    """
    Lista consolidada: todo técnico com visita registrada, com o vínculo de
    empresa ATIVO (se houver). Usada na tela do coordenador.
    """
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(text(QUERY_TECNICOS_CONSOLIDADO)).mappings().all()
    return [dict(linha) for linha in linhas]


def historico_tecnico(tecnico: str):
    """Histórico completo (ativos e encerrados) de vínculos de um técnico."""
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(
            text(QUERY_HISTORICO_TECNICO_EMPRESA), {"tecnico": tecnico}
        ).mappings().all()
    return [dict(linha) for linha in linhas]


def salvar_vinculo(tecnico: str, empresa: str, cnpj_empresa: str, data_inicio, criado_por: str, cpf: str = None):
    """
    Cria um novo vínculo ativo técnico-empresa.
    Se já existir um vínculo ativo para o técnico, o índice único
    uq_tecnico_empresa_ativo impede duplicidade — nesse caso o vínculo atual
    precisa ser desativado primeiro (ver desativar_vinculo).
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO tecnico_empresa
                    (tecnico, empresa, cnpj_empresa, cpf, data_inicio, criado_por)
                VALUES
                    (:tecnico, :empresa, :cnpj_empresa, :cpf, :data_inicio, :criado_por)
                """
            ),
            {
                "tecnico": tecnico,
                "empresa": empresa,
                "cnpj_empresa": cnpj_empresa or None,
                "cpf": cpf or None,
                "data_inicio": data_inicio,
                "criado_por": criado_por,
            },
        )


def vinculos_ativos_por_tecnicos(tecnicos: list[str]):
    """
    Empresa + CPF do vínculo ATIVO de cada técnico numa lista — usado na
    tela "Meus Técnicos" do supervisor para mostrar empresa/CPF sem
    depender da tela do coordenador. Retorna um dict tecnico -> linha.
    """
    if not tecnicos:
        return {}
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(
            text(QUERY_VINCULOS_ATIVOS_POR_TECNICOS), {"tecnicos": list(tecnicos)}
        ).mappings().all()
    return {linha["tecnico"]: dict(linha) for linha in linhas}


def desativar_vinculo(vinculo_id: int, motivo: str, data_fim):
    """Encerra o vínculo (nunca apaga) — grava data_fim e motivo."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE tecnico_empresa
                SET data_fim = :data_fim,
                    motivo_desvinculo = :motivo,
                    atualizado_em = NOW()
                WHERE id = :id
                """
            ),
            {"id": vinculo_id, "data_fim": data_fim, "motivo": motivo},
        )
