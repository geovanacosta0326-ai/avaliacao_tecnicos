"""
Consultas e ações do vínculo único do técnico (Gestão de Técnicos).

Substitui repositorio_tecnico_empresa.py e repositorio_tecnico_supervisor.py
— agora é uma tabela só (vinculo_tecnico), com todos os dados do vínculo
(CPF, projeto, atividade, empresa, CNPJ, supervisor, datas) juntos.
"""
from sqlalchemy import text
from app.database import get_engine
from app.repositorio import normalizar
from datetime import date

# Motivos padronizados de desvínculo (o formulário usa estes + "Outro").
MOTIVOS_DESVINCULACAO = [
    "Mudança de supervisor",
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

    Projeto/atividade: prioriza o que vem da base de visitas (mais
    atual); se o técnico ainda não tem visita registrada lá, cai pro
    que foi digitado na hora de criar o vínculo; se também não tiver,
    cai pro cadastro mestre do técnico (tecnico_atividades) — é o que
    alimenta a lista de "Projetos" do supervisor, então mantém os dois
    lugares consistentes.
    """
    engine = get_engine()
    query = f"""
        SELECT
            v.id AS vinculo_id, v.tecnico, v.cpf,
            COALESCE(vis.projeto_consolidado, v.projeto, cad.projeto) AS projeto,
            COALESCE(vis.atividade, v.atividade, cad.atividade) AS atividade,
            v.empresa, v.cnpj_empresa, v.supervisor,
            v.data_inicio, v.data_fim_prevista,
            v.data_desvinculacao, v.motivo_desvinculacao,
            vis.primeira_visita, vis.ultima_visita,
            tm.id_tecnico_responsavel AS id_tecnico, tm.ativo AS tecnico_ativo,
            tm.motivo_desativacao AS tecnico_motivo_desativacao, tm.data_desativacao AS tecnico_data_desativacao
        FROM vinculo_tecnico v
        LEFT JOIN ({QUERY_TODOS_TECNICOS_COM_VISITAS}) vis ON lower(trim(regexp_replace(vis.tecnico, '\\s+', ' ', 'g'))) = lower(trim(regexp_replace(v.tecnico, '\\s+', ' ', 'g')))
        LEFT JOIN LATERAL (
            SELECT ta.projeto, ta.atividade
            FROM tecnicos t
            JOIN tecnico_atividades ta ON ta.id_tecnico_responsavel = t.id_tecnico_responsavel
            WHERE lower(trim(regexp_replace(t.nome, '\\s+', ' ', 'g'))) = lower(trim(regexp_replace(v.tecnico, '\\s+', ' ', 'g')))
            ORDER BY ta.ultima_visita DESC NULLS LAST
            LIMIT 1
        ) cad ON true
        LEFT JOIN tecnicos tm ON lower(trim(regexp_replace(tm.nome, '\\s+', ' ', 'g'))) = lower(trim(regexp_replace(v.tecnico, '\\s+', ' ', 'g')))
        WHERE v.supervisor = :supervisor
        ORDER BY (v.data_desvinculacao IS NULL) DESC, v.tecnico, v.data_inicio DESC;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query), {"supervisor": supervisor}).mappings().all()
    return [dict(l) for l in linhas]


def listar_vinculos_de_todos_os_supervisores():
    """
    MESMA coisa que listar_vinculos_do_supervisor, mas pra TODOS os
    supervisores de uma vez só — usado nas telas que precisam mostrar
    vários supervisores juntos (ex: /coordenador/cadastros). Evita rodar
    a mesma consulta pesada (que varre toda a base de visitas) uma vez
    por supervisor — antes eram N consultas completas, uma por
    supervisor; agora é 1 consulta só, e o agrupamento por supervisor é
    feito em Python.

    Retorna um dict {supervisor: [vinculos...]}, na mesma ordem/formato
    de linha que listar_vinculos_do_supervisor.
    """
    engine = get_engine()
    query = f"""
        SELECT
            v.id AS vinculo_id, v.tecnico, v.cpf,
            COALESCE(vis.projeto_consolidado, v.projeto, cad.projeto) AS projeto,
            COALESCE(vis.atividade, v.atividade, cad.atividade) AS atividade,
            v.empresa, v.cnpj_empresa, v.supervisor,
            v.data_inicio, v.data_fim_prevista,
            v.data_desvinculacao, v.motivo_desvinculacao,
            vis.primeira_visita, vis.ultima_visita,
            tm.id_tecnico_responsavel AS id_tecnico, tm.ativo AS tecnico_ativo,
            tm.motivo_desativacao AS tecnico_motivo_desativacao, tm.data_desativacao AS tecnico_data_desativacao
        FROM vinculo_tecnico v
        LEFT JOIN ({QUERY_TODOS_TECNICOS_COM_VISITAS}) vis ON lower(trim(regexp_replace(vis.tecnico, '\\s+', ' ', 'g'))) = lower(trim(regexp_replace(v.tecnico, '\\s+', ' ', 'g')))
        LEFT JOIN LATERAL (
            SELECT ta.projeto, ta.atividade
            FROM tecnicos t
            JOIN tecnico_atividades ta ON ta.id_tecnico_responsavel = t.id_tecnico_responsavel
            WHERE lower(trim(regexp_replace(t.nome, '\\s+', ' ', 'g'))) = lower(trim(regexp_replace(v.tecnico, '\\s+', ' ', 'g')))
            ORDER BY ta.ultima_visita DESC NULLS LAST
            LIMIT 1
        ) cad ON true
        LEFT JOIN tecnicos tm ON lower(trim(regexp_replace(tm.nome, '\\s+', ' ', 'g'))) = lower(trim(regexp_replace(v.tecnico, '\\s+', ' ', 'g')))
        ORDER BY v.supervisor, (v.data_desvinculacao IS NULL) DESC, v.tecnico, v.data_inicio DESC;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query)).mappings().all()

    agrupado: dict[str, list[dict]] = {}
    for l in linhas:
        d = dict(l)
        agrupado.setdefault(d["supervisor"], []).append(d)
    return agrupado


def listar_tecnicos_sem_vinculo_ativo_com_este_supervisor(supervisor: str, mes_limite):
    """
    Técnicos que hoje são NATURALMENTE deste supervisor (pelo supervisor_atual
    da visita mais recente, na base de visitas) e que ainda não têm vínculo
    ativo com ele. Isso evita mostrar o técnico de todo mundo — só aparece
    quem já é do supervisor pela base de origem, esperando ser complementado
    com os dados do vínculo (projeto, atividade, empresa, CPF, datas).

    Só entram aqui os técnicos que JÁ FORAM DESVINCULADOS antes (por isso
    não entraram na vinculação automática) — os que nunca tiveram vínculo
    e têm visita recente já viram "Ativo" sozinhos.

    `mes_limite`: só mostra quem teve última visita a partir dessa data
    (calculado como "até 2 meses antes do mês atual") — evita acumular
    técnico antigo, sem visita há muito tempo, nessa lista.

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
          AND vis.ultima_visita >= :mes_limite
          AND vis.tecnico NOT IN (
              SELECT tecnico FROM vinculo_tecnico
              WHERE supervisor = :supervisor AND data_desvinculacao IS NULL
          )
        ORDER BY vis.tecnico;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query), {"supervisor": supervisor, "mes_limite": mes_limite}).mappings().all()
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
                    WHERE tecnico_responsavel = :tecnico
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


def reverter_desvinculacao(vinculo_id: int):
    """
    Desfaz um descredenciamento: limpa data/motivo, voltando o vínculo a
    ativo. Se o técnico já tiver outro vínculo ativo (ex: foi transferido
    depois), o índice único uq_vinculo_tecnico_ativo barra a operação —
    o chamador deve tratar essa exceção.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE vinculo_tecnico
                SET data_desvinculacao = NULL, motivo_desvinculacao = NULL
                WHERE id = :id;
            """),
            {"id": vinculo_id},
        )


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
            COALESCE(vis.projeto_consolidado, v.projeto, cad.projeto) AS projeto,
            COALESCE(vis.atividade, v.atividade, cad.atividade) AS atividade,
            v.empresa, v.cnpj_empresa, v.supervisor,
            v.data_inicio, v.data_fim_prevista,
            vis.primeira_visita, vis.ultima_visita
        FROM vinculo_tecnico v
        LEFT JOIN ({QUERY_TODOS_TECNICOS_COM_VISITAS}) vis ON lower(trim(regexp_replace(vis.tecnico, '\\s+', ' ', 'g'))) = lower(trim(regexp_replace(v.tecnico, '\\s+', ' ', 'g')))
        LEFT JOIN LATERAL (
            SELECT ta.projeto, ta.atividade
            FROM tecnicos t
            JOIN tecnico_atividades ta ON ta.id_tecnico_responsavel = t.id_tecnico_responsavel
            WHERE lower(trim(regexp_replace(t.nome, '\\s+', ' ', 'g'))) = lower(trim(regexp_replace(v.tecnico, '\\s+', ' ', 'g')))
            ORDER BY ta.ultima_visita DESC NULLS LAST
            LIMIT 1
        ) cad ON true
        WHERE v.data_desvinculacao IS NULL
        ORDER BY v.supervisor, v.tecnico;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query)).mappings().all()
    return [dict(l) for l in linhas]


def listar_historico_desvinculacoes():
    """
    Auditoria do coordenador: TODO desvínculo já registrado no sistema,
    de todos os técnicos — inclusive quem foi desvinculado e no mesmo dia
    (ou depois) ganhou um vínculo novo com outro supervisor (transferência,
    motivo "Mudança de supervisor"). Isso é diferente de
    listar_tecnicos_descredenciados(), que só traz quem está SEM
    supervisor agora — aqui aparece o evento em si, tenha ele resultado
    em técnico solto ou em transferência.
    Traz junto (quando existir) o supervisor atual do técnico, pra deixar
    claro que ele não ficou sem vínculo, só trocou.

    NÃO entra aqui o vínculo que foi encerrado automaticamente porque o
    técnico foi DESATIVADO (motivo começando com "Técnico desativado") —
    esse evento já aparece na lista de "Desativados"; repetir aqui só
    duplicava a mesma informação e confundia o coordenador.
    """
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(
            text("""
                SELECT
                    v.tecnico,
                    v.supervisor AS supervisor_anterior,
                    v.data_inicio,
                    v.data_desvinculacao,
                    v.motivo_desvinculacao,
                    atual.supervisor AS supervisor_atual
                FROM vinculo_tecnico v
                LEFT JOIN vinculo_tecnico atual
                    ON atual.tecnico = v.tecnico
                   AND atual.data_desvinculacao IS NULL
                WHERE v.data_desvinculacao IS NOT NULL
                  AND (v.motivo_desvinculacao IS NULL
                       OR v.motivo_desvinculacao NOT LIKE 'Técnico desativado%')
                ORDER BY v.data_desvinculacao DESC, v.tecnico;
            """)
        ).mappings().all()
    return [dict(l) for l in linhas]


def auto_desvincular_tecnicos_inativos(supervisor: str, mes_limite) -> int:
    """
    Desvincula automaticamente (mantendo o histórico, nunca apaga) todo
    técnico que está ATIVO com este supervisor mas NÃO tem visita recente
    (>= mes_limite) — seja porque parou de visitar, seja porque não tem
    visita nenhuma registrada pra ele.

    Isso é o "espelho" do auto_vincular_tecnicos_recentes: um cuida de
    trazer quem começou a aparecer, o outro cuida de tirar quem sumiu.

    Retorna quantos técnicos foram desvinculados agora.
    """
    engine = get_engine()
    query = f"""
        SELECT v.id AS vinculo_id, v.tecnico
        FROM vinculo_tecnico v
        LEFT JOIN ({QUERY_TODOS_TECNICOS_COM_VISITAS}) vis ON lower(trim(regexp_replace(vis.tecnico, '\\s+', ' ', 'g'))) = lower(trim(regexp_replace(v.tecnico, '\\s+', ' ', 'g')))
        WHERE v.supervisor = :supervisor
          AND v.data_desvinculacao IS NULL
          AND (vis.ultima_visita IS NULL OR vis.ultima_visita < :mes_limite);
    """
    with engine.connect() as conn:
        inativos = conn.execute(text(query), {"supervisor": supervisor, "mes_limite": mes_limite}).mappings().all()

    processados = 0
    for i in inativos:
        try:
            desvincular_vinculo(
                vinculo_id=i["vinculo_id"],
                data_desvinculacao=date.today(),
                motivo="Sem visita nos últimos 2 meses (desvinculado automaticamente)",
            )
            processados += 1
        except Exception:
            continue

    return processados


def auto_vincular_tecnicos_recentes(supervisor: str, mes_limite) -> int:
    """
    Vincula automaticamente (sem o supervisor precisar clicar em nada) todo
    técnico cuja visita mais recente (dentro do período recente, mes_limite)
    aponta este supervisor como responsável (supervisor_atual). Cobre dois
    casos:

    1) Técnico NUNCA teve nenhum vínculo (ativo ou encerrado) com este
       supervisor, e não está ativo com nenhum outro agora — cria um vínculo
       novo direto.

    2) Técnico está com vínculo ATIVO em OUTRO supervisor, mas a visita mais
       recente já aponta para este supervisor (ou seja, ele mudou de equipe
       na base de visitas) — o sistema ENCERRA o vínculo antigo (guardando
       o histórico, nunca apaga) com o motivo "Mudança de supervisor
       (conforme visita mais recente)", e cria um vínculo novo aqui.

    Isso NÃO reativa técnico que o PRÓPRIO supervisor atual já desvinculou
    antes — esse continua parado em "Não vinculado" até ele vincular de novo
    manualmente (o desvincular é uma decisão que "vale", não é sobrescrita
    automaticamente só porque ele segue visitando).

    Projeto/atividade entram já preenchidos com a sugestão da visita mais
    recente; CPF/empresa/CNPJ ficam em branco — o supervisor edita quando
    quiser (tem autonomia total sobre esses dados).

    Retorna quantos técnicos foram vinculados (criados ou migrados) agora.
    """
    engine = get_engine()

    # Caso 1: nunca teve vínculo nenhum com este supervisor, e não está
    # ativo com ninguém agora.
    query_novos = f"""
        SELECT vis.tecnico, vis.primeira_visita, vis.projeto_consolidado, vis.atividade
        FROM ({QUERY_TODOS_TECNICOS_COM_VISITAS}) vis
        WHERE vis.supervisor_atual = :supervisor
          AND vis.ultima_visita >= :mes_limite
          AND vis.tecnico NOT IN (
              SELECT tecnico FROM vinculo_tecnico WHERE supervisor = :supervisor
          )
          AND vis.tecnico NOT IN (
              SELECT tecnico FROM vinculo_tecnico WHERE data_desvinculacao IS NULL
          );
    """

    # Caso 2: está ativo com OUTRO supervisor, mas a visita recente já
    # aponta para este supervisor — precisa migrar.
    query_migrar = f"""
        SELECT vis.tecnico, vis.primeira_visita, vis.projeto_consolidado, vis.atividade,
               v_antigo.id AS vinculo_antigo_id, v_antigo.supervisor AS supervisor_antigo
        FROM ({QUERY_TODOS_TECNICOS_COM_VISITAS}) vis
        JOIN vinculo_tecnico v_antigo
            ON v_antigo.tecnico = vis.tecnico
            AND v_antigo.data_desvinculacao IS NULL
            AND v_antigo.supervisor <> :supervisor
        WHERE vis.supervisor_atual = :supervisor
          AND vis.ultima_visita >= :mes_limite;
    """

    with engine.connect() as conn:
        candidatos_novos = conn.execute(
            text(query_novos), {"supervisor": supervisor, "mes_limite": mes_limite}
        ).mappings().all()
        candidatos_migrar = conn.execute(
            text(query_migrar), {"supervisor": supervisor, "mes_limite": mes_limite}
        ).mappings().all()

    processados = 0

    for c in candidatos_novos:
        try:
            criar_vinculo(
                tecnico=c["tecnico"],
                supervisor=supervisor,
                data_inicio=c["primeira_visita"],
                criado_por="sistema (auto-vínculo por visita recente)",
                projeto=c["projeto_consolidado"],
                atividade=c["atividade"],
            )
            processados += 1
        except Exception:
            # Não deixa uma falha pontual (ex: condição de corrida rara)
            # travar a tela inteira — só pula esse técnico dessa vez.
            continue

    for c in candidatos_migrar:
        try:
            desvincular_vinculo(
                vinculo_id=c["vinculo_antigo_id"],
                data_desvinculacao=date.today(),
                motivo=f"Mudança de supervisor (visita mais recente aponta para {supervisor})",
            )
            criar_vinculo(
                tecnico=c["tecnico"],
                supervisor=supervisor,
                data_inicio=c["primeira_visita"],
                criado_por="sistema (auto-vínculo por mudança de supervisor)",
                projeto=c["projeto_consolidado"],
                atividade=c["atividade"],
            )
            processados += 1
        except Exception:
            continue

    return processados


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
    empresa: str = None, cnpj_empresa: str = None, data_inicio=None, data_fim_prevista=None,
):
    """
    Atualiza os dados do vínculo ATIVO (corrigir projeto, atividade,
    empresa, CNPJ, CPF, início, data prevista de fim) — não cria um novo
    registro histórico, é edição do vínculo corrente. Desvincular é uma
    ação separada (ver desvincular_vinculo).
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE vinculo_tecnico
                SET cpf = :cpf, projeto = :projeto, atividade = :atividade,
                    empresa = :empresa, cnpj_empresa = :cnpj_empresa,
                    data_inicio = COALESCE(:data_inicio, data_inicio),
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
                "data_inicio": data_inicio or None,
                "data_fim_prevista": data_fim_prevista or None,
            },
        )


def editar_datas_vinculo(vinculo_id: int, data_inicio=None, data_fim_prevista=None):
    """
    Atualiza SÓ o início e o fim previsto do vínculo ativo — não mexe em
    projeto/atividade/empresa/CNPJ/CPF (esses vêm da base de visitas ou
    do cadastro mestre do técnico, não fazem sentido editar por aqui).
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE vinculo_tecnico
                SET data_inicio = COALESCE(:data_inicio, data_inicio),
                    data_fim_prevista = :data_fim_prevista,
                    atualizado_em = NOW()
                WHERE id = :id
            """),
            {
                "id": vinculo_id,
                "data_inicio": data_inicio or None,
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