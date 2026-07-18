"""
Consultas e ações do vínculo único do técnico (Gestão de Técnicos).

Substitui repositorio_tecnico_empresa.py e repositorio_tecnico_supervisor.py
— agora é uma tabela só (vinculo_tecnico), com todos os dados do vínculo
(CPF, projeto, atividade, empresa, CNPJ, supervisor, datas) juntos.
"""
from sqlalchemy import text
from app.database import get_engine
from app.repositorio import normalizar

# Motivos padronizados de desvínculo (o formulário usa estes + "Outro").
MOTIVOS_DESVINCULACAO = [
    "Encerramento do projeto",
    "Fim de contrato",
    "Substituição do técnico",
    "Desligamento da empresa",
    "Mudança de atividade",
    "Solicitação da empresa",
]

# Todo técnico com pelo menos uma visita registrada: projeto/atividade/supervisor
# da visita MAIS RECENTE (isso define o "projeto atual"), última visita geral, e
# primeira visita DENTRO DESSE PROJETO ATUAL — não a primeira visita de todos os
# tempos, porque um técnico pode ter passado por projetos diferentes antes, e
# misturar esse histórico dava uma "1ª visita" enganosa (de um projeto antigo,
# diferente do que ele está agora).
QUERY_TODOS_TECNICOS_COM_VISITAS = """
WITH visitas AS (
    SELECT
        tecnico_responsavel AS tecnico,
        dt_visita_v,
        projeto_consolidado,
        FIRST_VALUE(projeto_consolidado) OVER (
            PARTITION BY tecnico_responsavel ORDER BY dt_visita_v DESC
        ) AS projeto_atual,
        FIRST_VALUE(atividade) OVER (
            PARTITION BY tecnico_responsavel ORDER BY dt_visita_v DESC
        ) AS atividade_atual,
        FIRST_VALUE(supervisor_atual) OVER (
            PARTITION BY tecnico_responsavel ORDER BY dt_visita_v DESC
        ) AS supervisor_mais_recente,
        MAX(dt_visita_v) OVER (PARTITION BY tecnico_responsavel) AS ultima_visita
    FROM public.acompanhamento_mensal_visitas
    WHERE tecnico_responsavel IS NOT NULL
)
SELECT DISTINCT ON (tecnico)
    tecnico,
    MIN(dt_visita_v) FILTER (WHERE projeto_consolidado IS NOT DISTINCT FROM projeto_atual)
        OVER (PARTITION BY tecnico) AS primeira_visita,
    ultima_visita,
    projeto_atual AS projeto_consolidado,
    atividade_atual AS atividade,
    supervisor_mais_recente AS supervisor_atual
FROM visitas
ORDER BY tecnico, dt_visita_v DESC
"""


def listar_todos_tecnicos_com_visitas():
    """Todo técnico com visita registrada + primeira/última visita."""
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(text(QUERY_TODOS_TECNICOS_COM_VISITAS)).mappings().all()
    return [dict(l) for l in linhas]


def listar_vinculos_do_supervisor(supervisor: str):
    """
    TODOS os vínculos deste supervisor — ativos e encerrados — com
    primeira/última visita. A tela "Gestão de Técnicos" separa ativos de
    históricos a partir do campo data_desvinculacao.
    """
    engine = get_engine()
    query = f"""
        SELECT
            v.id AS vinculo_id, v.tecnico, v.cpf,
            COALESCE(vis.projeto_consolidado, v.projeto) AS projeto,
            COALESCE(vis.atividade, v.atividade) AS atividade,
            v.empresa, v.cnpj_empresa, v.supervisor,
            v.data_inicio, v.data_fim_prevista,
            v.data_desvinculacao, v.motivo_desvinculacao,
            vis.primeira_visita, vis.ultima_visita
        FROM vinculo_tecnico v
        LEFT JOIN ({QUERY_TODOS_TECNICOS_COM_VISITAS}) vis ON vis.tecnico = v.tecnico
        WHERE v.supervisor = :supervisor
        ORDER BY (v.data_desvinculacao IS NULL) DESC, v.tecnico, v.data_inicio DESC;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query), {"supervisor": supervisor}).mappings().all()
    return [dict(l) for l in linhas]


def listar_tecnicos_sem_vinculo_ativo_com_este_supervisor(supervisor: str):
    """
    Técnicos que hoje são NATURALMENTE deste supervisor (pelo supervisor_atual
    da visita mais recente, na base de visitas) e que ainda não têm vínculo
    ativo com ele. Isso evita mostrar o técnico de todo mundo — só aparece
    quem já é do supervisor pela base de origem, esperando ser complementado
    com os dados do vínculo (projeto, atividade, empresa, CPF, datas).

    Também traz projeto_consolidado e atividade da visita mais recente, para
    sugerir no formulário de complementar cadastro (o supervisor pode ajustar).
    """
    engine = get_engine()
    query = f"""
        SELECT
            vis.tecnico, vis.primeira_visita, vis.ultima_visita,
            vis.projeto_consolidado, vis.atividade,
            v_outro.supervisor AS supervisor_atual_de_outro
        FROM ({QUERY_TODOS_TECNICOS_COM_VISITAS}) vis
        LEFT JOIN vinculo_tecnico v_outro
            ON v_outro.tecnico = vis.tecnico AND v_outro.data_desvinculacao IS NULL
        WHERE vis.supervisor_atual = :supervisor
          AND vis.tecnico NOT IN (
              SELECT tecnico FROM vinculo_tecnico
              WHERE supervisor = :supervisor AND data_desvinculacao IS NULL
          )
        ORDER BY vis.tecnico;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query), {"supervisor": supervisor}).mappings().all()
    return [dict(l) for l in linhas]


def resolver_nome_tecnico(tecnico_recebido: str) -> str | None:
    """
    Acha o nome EXATO do técnico (como está gravado na base de visitas),
    a partir de um nome recebido (ex: vindo da URL, que pode ter vindo
    com acentuação/espaços diferentes). Retorna None se não achar.
    """
    todos = listar_todos_tecnicos_com_visitas()
    alvo = normalizar(tecnico_recebido)
    for t in todos:
        if normalizar(t["tecnico"]) == alvo:
            return t["tecnico"]
    return None


def obter_visita_tecnico(tecnico: str):
    """Primeira visita (dentro do projeto atual) + última visita + projeto/atividade atuais de UM técnico."""
    engine = get_engine()
    with engine.connect() as conn:
        linha = conn.execute(
            text("""
                WITH visitas AS (
                    SELECT
                        tecnico_responsavel AS tecnico,
                        dt_visita_v,
                        projeto_consolidado,
                        FIRST_VALUE(projeto_consolidado) OVER (
                            PARTITION BY tecnico_responsavel ORDER BY dt_visita_v DESC
                        ) AS projeto_atual,
                        FIRST_VALUE(atividade) OVER (
                            PARTITION BY tecnico_responsavel ORDER BY dt_visita_v DESC
                        ) AS atividade_atual,
                        FIRST_VALUE(supervisor_atual) OVER (
                            PARTITION BY tecnico_responsavel ORDER BY dt_visita_v DESC
                        ) AS supervisor_mais_recente,
                        MAX(dt_visita_v) OVER (PARTITION BY tecnico_responsavel) AS ultima_visita
                    FROM public.acompanhamento_mensal_visitas
                    WHERE tecnico_responsavel = :tecnico
                )
                SELECT DISTINCT ON (tecnico)
                    tecnico,
                    MIN(dt_visita_v) FILTER (WHERE projeto_consolidado IS NOT DISTINCT FROM projeto_atual)
                        OVER (PARTITION BY tecnico) AS primeira_visita,
                    ultima_visita,
                    projeto_atual AS projeto_consolidado,
                    atividade_atual AS atividade,
                    supervisor_mais_recente AS supervisor_atual
                FROM visitas
                ORDER BY tecnico, dt_visita_v DESC
            """),
            {"tecnico": tecnico},
        ).mappings().first()
    return dict(linha) if linha else {
        "primeira_visita": None, "ultima_visita": None,
        "projeto_consolidado": None, "atividade": None, "supervisor_atual": None,
    }


def obter_vinculo_ativo_do_tecnico(tecnico: str):
    """
    O vínculo ATIVO de um técnico, seja com qual for o supervisor —
    usado na tela de detalhe pra saber se o técnico já está "tomado"
    por outro supervisor antes de permitir vincular.

    Comparação tolerante a acento/maiúsculas/espaços (o nome pode chegar
    um pouco diferente vindo da URL) — mesma lógica usada em outras
    partes do sistema para achar o técnico correto.
    """
    alvo = normalizar(tecnico)
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(
            text("""
                SELECT * FROM vinculo_tecnico
                WHERE data_desvinculacao IS NULL
            """)
        ).mappings().all()
    for linha in linhas:
        if normalizar(linha["tecnico"]) == alvo:
            return dict(linha)
    return None


def obter_vinculo(vinculo_id: int):
    """Um vínculo específico (usado para pré-preencher o formulário de edição)."""
    engine = get_engine()
    with engine.connect() as conn:
        linha = conn.execute(
            text("SELECT * FROM vinculo_tecnico WHERE id = :id"), {"id": vinculo_id}
        ).mappings().first()
    return dict(linha) if linha else None


def historico_tecnico(tecnico: str):
    """Todo o histórico de vínculos (ativos e encerrados) de um técnico — auditoria."""
    alvo = normalizar(tecnico)
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(
            text("""
                SELECT * FROM vinculo_tecnico
                ORDER BY data_inicio DESC;
            """)
        ).mappings().all()
    return [dict(l) for l in linhas if normalizar(l["tecnico"]) == alvo]


def listar_todos_vinculos_ativos():
    """Auditoria do coordenador: todos os vínculos ativos, de todos os supervisores."""
    engine = get_engine()
    query = f"""
        SELECT
            v.id AS vinculo_id, v.tecnico, v.cpf,
            COALESCE(vis.projeto_consolidado, v.projeto) AS projeto,
            COALESCE(vis.atividade, v.atividade) AS atividade,
            v.empresa, v.cnpj_empresa, v.supervisor,
            v.data_inicio, v.data_fim_prevista,
            vis.primeira_visita, vis.ultima_visita
        FROM vinculo_tecnico v
        LEFT JOIN ({QUERY_TODOS_TECNICOS_COM_VISITAS}) vis ON vis.tecnico = v.tecnico
        WHERE v.data_desvinculacao IS NULL
        ORDER BY v.supervisor, v.tecnico;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query)).mappings().all()
    return [dict(l) for l in linhas]


def criar_vinculo(
    tecnico: str, supervisor: str, data_inicio, criado_por: str,
    cpf: str = None, projeto: str = None, atividade: str = None,
    empresa: str = None, cnpj_empresa: str = None, data_fim_prevista=None,
):
    """
    Cria um novo vínculo ativo. Se o técnico já tiver um vínculo ativo
    (com este ou outro supervisor), o índice único uq_vinculo_tecnico_ativo
    impede duplicidade — é preciso desvincular o vínculo atual primeiro.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO vinculo_tecnico
                    (tecnico, cpf, projeto, atividade, empresa, cnpj_empresa,
                     supervisor, data_inicio, data_fim_prevista, criado_por)
                VALUES
                    (:tecnico, :cpf, :projeto, :atividade, :empresa, :cnpj_empresa,
                     :supervisor, :data_inicio, :data_fim_prevista, :criado_por)
            """),
            {
                "tecnico": tecnico,
                "cpf": cpf or None,
                "projeto": projeto or None,
                "atividade": atividade or None,
                "empresa": empresa or None,
                "cnpj_empresa": cnpj_empresa or None,
                "supervisor": supervisor,
                "data_inicio": data_inicio,
                "data_fim_prevista": data_fim_prevista or None,
                "criado_por": criado_por,
            },
        )


def editar_vinculo(
    vinculo_id: int, cpf: str = None, projeto: str = None, atividade: str = None,
    empresa: str = None, cnpj_empresa: str = None, data_fim_prevista=None,
):
    """
    Atualiza os dados do vínculo ATIVO (corrigir projeto, atividade,
    empresa, CNPJ, CPF, data prevista de fim) — não cria um novo registro
    histórico, é edição do vínculo corrente. Desvincular é uma ação
    separada (ver desvincular_vinculo).
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE vinculo_tecnico
                SET cpf = :cpf, projeto = :projeto, atividade = :atividade,
                    empresa = :empresa, cnpj_empresa = :cnpj_empresa,
                    data_fim_prevista = :data_fim_prevista,
                    atualizado_em = NOW()
                WHERE id = :id
            """),
            {
                "id": vinculo_id,
                "cpf": cpf or None,
                "projeto": projeto or None,
                "atividade": atividade or None,
                "empresa": empresa or None,
                "cnpj_empresa": cnpj_empresa or None,
                "data_fim_prevista": data_fim_prevista or None,
            },
        )


def desvincular_vinculo(vinculo_id: int, data_desvinculacao, motivo: str):
    """Encerra o vínculo (nunca apaga) — grava data_desvinculacao e motivo."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE vinculo_tecnico
                SET data_desvinculacao = :data_desvinculacao,
                    motivo_desvinculacao = :motivo,
                    atualizado_em = NOW()
                WHERE id = :id
            """),
            {"id": vinculo_id, "data_desvinculacao": data_desvinculacao, "motivo": motivo},
        )