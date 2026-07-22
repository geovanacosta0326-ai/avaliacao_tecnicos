"""
Consultas ao banco de dados operacional (acompanhamento_mensal_visitas).

A regra de "quem é o supervisor de cada técnico" é a MESMA usada no
painel de ranking original: pega o supervisor_atual da visita mais
recente de cada técnico (DISTINCT ON ... ORDER BY dt_visita DESC).
"""
import unicodedata
from datetime import date
from sqlalchemy import text
from app.database import get_engine


def rodar_migracoes_unicas():
    """
    Garante colunas que algumas telas precisam, mas SEM rodar isso a cada
    clique — isso deve ser chamado UMA VEZ, no startup do FastAPI
    (ver app/main.py). Antes, cada leitura/gravação de técnico desativado
    fazia um ALTER TABLE próprio, e cada ALTER TABLE — mesmo com
    IF NOT EXISTS, mesmo não mudando nada na prática — precisa de lock
    exclusivo na tabela inteira. Se qualquer conexão ficasse presa
    ("idle in transaction"), isso travava toda tela que mexesse em
    técnico, coordenador incluído. Rodando uma vez só no startup, esse
    lock só acontece na subida do servidor, nunca durante o uso normal.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS motivo_desativacao TEXT;"))
        conn.execute(text("ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS data_desativacao DATE;"))
        # Mês/ano da capacitação metodológica do técnico e a modalidade em
        # que ela foi realizada (Presencial/Online) — preenchidos pelo
        # supervisor no cadastro do técnico.
        conn.execute(text("ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS mes_ano_capacitacao_metodologica DATE;"))
        conn.execute(text("ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS modalidade_capacitacao_metodologica TEXT;"))
        # nota_final passou a ser a MÉDIA das 10 perguntas (5.0 a 10.0),
        # não mais a soma (50 a 100) — a coluna precisa aceitar decimais.
        conn.execute(text("ALTER TABLE avaliacoes_tecnicos ALTER COLUMN nota_final TYPE NUMERIC(4,2);"))


def normalizar(texto: str) -> str:
    """
    Normaliza texto para comparação robusta de nomes (técnico, supervisor etc).

    Resolve os casos mais comuns de "mesmo nome, string diferente":
      - acentuação vinda de decodificação diferente na URL (NFC vs NFD)
      - espaços extras no início/fim ou duplicados no meio
      - diferença de maiúsculas/minúsculas

    NÃO deve ser usado como o valor a salvar no banco — serve só para
    comparar/localizar o registro; o nome "oficial" continua sendo o
    que está armazenado na tabela.
    """
    if texto is None:
        return ""
    texto = unicodedata.normalize("NFC", texto).strip()
    texto = " ".join(texto.split())  # colapsa espaços internos duplicados
    return texto.casefold()


def encontrar_tecnico(tecnico_recebido: str, tecnicos_permitidos: list[str]) -> str | None:
    """
    Localiza, dentro de tecnicos_permitidos, o nome EXATO (do banco) que
    corresponde a tecnico_recebido (ex: vindo da URL), usando comparação
    normalizada em vez de igualdade estrita de string.

    Retorna o nome canônico (como está no banco) ou None se não achar.
    """
    alvo = normalizar(tecnico_recebido)
    for t in tecnicos_permitidos:
        if normalizar(t) == alvo:
            return t
    return None

# ══════════════════════════════════════════════════════════
# Supervisor mais recente de cada técnico (mesma regra do rank)
# ══════════════════════════════════════════════════════════
QUERY_SUPERVISOR_POR_TECNICO = """
SELECT DISTINCT ON (tecnico_responsavel)
    tecnico_responsavel AS tecnico,
    supervisor_atual     AS supervisor
FROM public.acompanhamento_mensal_visitas
WHERE tecnico_responsavel IS NOT NULL
  AND supervisor_atual IS NOT NULL
ORDER BY tecnico_responsavel, dt_visita DESC, ctid DESC
"""


def listar_supervisores():
    """Lista todos os supervisores distintos que existem hoje na base."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT DISTINCT supervisor
            FROM ({QUERY_SUPERVISOR_POR_TECNICO}) base
            ORDER BY supervisor;
        """)).fetchall()
    return [r.supervisor for r in rows]


def listar_tecnicos_do_supervisor(supervisor: str):
    """
    Lista os técnicos ATIVOS na equipe deste supervisor.

    Vem do vínculo único (vinculo_tecnico) — só entra aqui quem tem
    vínculo ativo (data_desvinculacao IS NULL). Um técnico desvinculado
    some desta lista dali em diante, mas as avaliações já lançadas para
    ele continuam intactas no histórico (avaliacoes_tecnicos não depende
    do vínculo, guarda supervisor+tecnico+mês na hora do lançamento).
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tecnico
                FROM vinculo_tecnico
                WHERE supervisor = :supervisor
                  AND data_desvinculacao IS NULL
                ORDER BY tecnico;
            """),
            {"supervisor": supervisor},
        ).fetchall()
    return [r.tecnico for r in rows]


def listar_tecnicos_avaliados_pelo_supervisor(supervisor: str):
    """
    Lista TODOS os técnicos que este supervisor já avaliou alguma vez,
    independente de vínculo estar ativo ou não hoje. Usado em telas de
    histórico/comparação (ex: "Comparar meses"), onde o supervisor deve
    poder ver avaliações que ele mesmo lançou no passado, mesmo que o
    técnico tenha sido desvinculado depois.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT tecnico
                FROM avaliacoes_tecnicos
                WHERE supervisor = :supervisor
                ORDER BY tecnico;
            """),
            {"supervisor": supervisor},
        ).fetchall()
    return [r.tecnico for r in rows]


def mes_referencia_atual() -> date:
    """
    A avaliação é sempre referente ao MÊS ANTERIOR ao mês corrente.
    Retorna sempre o dia 1 desse mês (ex: hoje=15/07/2026 -> 01/06/2026).
    """
    hoje = date.today()
    ano = hoje.year if hoje.month > 1 else hoje.year - 1
    mes = hoje.month - 1 if hoje.month > 1 else 12
    return date(ano, mes, 1)


def mes_anterior(ref: date) -> date:
    """Retorna o dia 1 do mês imediatamente anterior a `ref`."""
    ano = ref.year if ref.month > 1 else ref.year - 1
    mes = ref.month - 1 if ref.month > 1 else 12
    return date(ano, mes, 1)


def meses_disponiveis_para_avaliacao(qtd: int = 6) -> list[date]:
    """
    Lista os últimos `qtd` meses que podem ser escolhidos na hora de avaliar
    (o mês corrente nunca entra, pois só se avalia mês já fechado).
    Ordem: mais recente primeiro (o primeiro é o padrão/sugerido).
    """
    meses = []
    m = mes_referencia_atual()
    for _ in range(qtd):
        meses.append(m)
        m = mes_anterior(m)
    return meses


# ══════════════════════════════════════════════════════════
# RESUMO DE VISITAS DO TÉCNICO NO MÊS (mostrado ao abrir a tela de
# avaliação) — total de visitas, visitas válidas/inválidas, orientações
# (total e concluídas) e propriedades (total/ativas/inativas).
#
# IMPORTANTE: o fim do período NUNCA passa de hoje (CURRENT_DATE).
# Se o mês escolhido (mes_ref) já fechou (caso normal, já que só se
# avalia mês anterior), fim_mes = último dia do mês mesmo. Mas se um
# dia esse filtro passar a aceitar o mês corrente (ainda em andamento),
# fim_mes vira hoje — nunca o dia 30/31 completo, que ainda não
# aconteceu. Isso evita "buracos" e datas fantasmas no meio do mês.
# ══════════════════════════════════════════════════════════
def resumo_visitas_tecnico(tecnico: str, mes_ref: date) -> dict | None:
    """
    Resumo agregado das visitas de UM técnico no mes_ref escolhido na
    tela de avaliação. Mesma régua usada na auditoria/sincronização
    (flg_coleta_dados = 'Não'), só que recortada para um único técnico
    e um único mês, em vez de rodar para a base inteira.

    EXCEÇÃO: `ultima_visita` NÃO fica presa ao mes_ref — o banco não
    amarra a última visita do técnico ao mês em avaliação (ele pode
    ter visitado depois, ou o mês escolhido pode não ter nenhuma visita
    ainda assim). Por isso ela é buscada à parte, no histórico completo,
    igual ao resto do sistema faz (sincronizar_tecnicos_da_visita etc).
    """
    import calendar
    inicio_mes = date(mes_ref.year, mes_ref.month, 1)
    ultimo_dia_mes = date(
        mes_ref.year, mes_ref.month,
        calendar.monthrange(mes_ref.year, mes_ref.month)[1],
    )
    fim_mes = min(ultimo_dia_mes, date.today())  # nunca passa do dia de hoje

    engine = get_engine()
    with engine.connect() as conn:
        # Última visita real do técnico — histórico completo, sem olhar
        # para o mês de referência escolhido na tela.
        ultima_visita_geral = conn.execute(
            text("""
                SELECT MAX(dt_visita_v::date) AS ultima_visita
                FROM public.acompanhamento_mensal_visitas
                WHERE tecnico_responsavel = :tecnico
                  AND dt_visita_v::date <= CURRENT_DATE
                  AND flg_coleta_dados = 'Não';
            """),
            {"tecnico": tecnico},
        ).scalar()

        row = conn.execute(
            text("""
                WITH base AS (
                    SELECT *
                    FROM public.acompanhamento_mensal_visitas
                    WHERE tecnico_responsavel = :tecnico
                      AND dt_visita_v::date BETWEEN :inicio_mes AND :fim_mes
                      AND flg_coleta_dados = 'Não'
                ),
                propriedade_projeto AS (
                    -- Quantos projetos distintos passaram por cada propriedade
                    -- deste técnico no período. > 1 = propriedade "repetida"
                    -- em mais de um projeto (sobreposição).
                    SELECT id_propriedade, COUNT(DISTINCT projeto) AS qtd_projetos
                    FROM base
                    GROUP BY id_propriedade
                )
                SELECT
                    MAX(b.supervisor) AS supervisor,
                    STRING_AGG(DISTINCT b.projeto, ', ')   AS projetos,
                    STRING_AGG(DISTINCT b.atividade, ', ') AS atividades,

                    SUM(COALESCE(b.ori_total_geral, 0)) AS ori_total_geral,
                    SUM(COALESCE(b.ori_concluida, 0))   AS ori_concluida,

                    COUNT(DISTINCT b.id_propriedade) AS total_propriedades,
                    COUNT(DISTINCT CASE WHEN b.vinculo_dt_fim IS NULL     THEN b.id_propriedade END) AS propriedades_ativas,
                    COUNT(DISTINCT CASE WHEN b.vinculo_dt_fim IS NOT NULL THEN b.id_propriedade END) AS propriedades_inativas,

                    COUNT(DISTINCT b.id_visita) AS total_visitas,
                    COUNT(DISTINCT CASE
                        WHEN b.visita_valida IN ('Valida', 'Validada') THEN b.id_visita
                    END) AS total_visitas_validas,
                    COUNT(DISTINCT CASE WHEN b.visita_valida = 'Invalida' THEN b.id_visita END) AS visitas_invalidas,

                    MIN(b.dt_visita_v::date) AS primeira_visita,

                    (SELECT COUNT(*) FROM propriedade_projeto WHERE qtd_projetos > 1) AS propriedades_com_sobreposicao
                FROM base b
                GROUP BY b.tecnico_responsavel;
            """),
            {"tecnico": tecnico, "inicio_mes": inicio_mes, "fim_mes": fim_mes},
        ).mappings().fetchone()

    if row is None:
        # Sem visita registrada NESTE mês específico — mas ainda assim
        # mostramos a última visita real do técnico (histórico), em vez
        # de simplesmente esconder essa informação.
        if ultima_visita_geral is None:
            return None
        return {
            "supervisor": None,
            "projetos": None,
            "atividades": None,
            "ori_total_geral": 0,
            "ori_concluida": 0,
            "total_propriedades": 0,
            "propriedades_ativas": 0,
            "propriedades_inativas": 0,
            "total_visitas": 0,
            "total_visitas_validas": 0,
            "visitas_invalidas": 0,
            "primeira_visita": None,
            "ultima_visita": ultima_visita_geral,
            "propriedades_com_sobreposicao": 0,
            "pct_visitas_validas": None,
            "pct_ori_concluida": None,
            "pct_propriedades_ativas": None,
            "pct_propriedades_sem_sobreposicao": None,
        }

    resultado = dict(row)
    resultado["ultima_visita"] = ultima_visita_geral  # histórico completo, não o mês filtrado

    total_visitas = resultado.get("total_visitas") or 0
    total_propriedades = resultado.get("total_propriedades") or 0
    sobrepostas = resultado.get("propriedades_com_sobreposicao") or 0
    total_ori = resultado.get("ori_total_geral") or 0

    # % de visitas válidas sobre o total de visitas do período.
    resultado["pct_visitas_validas"] = (
        round(resultado.get("total_visitas_validas", 0) / total_visitas * 100, 1)
        if total_visitas else None
    )
    # % de orientações concluídas sobre o total de orientações do período.
    resultado["pct_ori_concluida"] = (
        round(resultado.get("ori_concluida", 0) / total_ori * 100, 1)
        if total_ori else None
    )
    # % de propriedades ativas sobre o total de propriedades atendidas.
    resultado["pct_propriedades_ativas"] = (
        round(resultado.get("propriedades_ativas", 0) / total_propriedades * 100, 1)
        if total_propriedades else None
    )
    # % de propriedades SEM sobreposição de projeto — ou seja, o inverso
    # do flag_propriedade_mais_projeto (que só dizia sim/não). Aqui é o
    # percentual real: quantas propriedades o técnico atende que NÃO
    # aparecem em mais de um projeto ao mesmo tempo.
    resultado["pct_propriedades_sem_sobreposicao"] = (
        round((total_propriedades - sobrepostas) / total_propriedades * 100, 1)
        if total_propriedades else None
    )

    return resultado


# ══════════════════════════════════════════════════════════
# PRAZO DE AVALIAÇÃO E AUTORIZAÇÃO DO COORDENADOR
#
# Regra: o supervisor sempre avalia os técnicos das visitas do mês
# ANTERIOR. Ele tem até o "dia-limite" (configurável, padrão dia 23)
# do mês seguinte para lançar essa avaliação. Depois disso, só
# consegue lançar se o coordenador autorizar aquele supervisor+mês
# especificamente.
# ══════════════════════════════════════════════════════════
def obter_dia_limite() -> int:
    """Lê o dia-limite configurado (padrão 23 se a tabela ainda não existir)."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT dia_limite FROM configuracao_prazo_avaliacao WHERE id = 1;")
        ).fetchone()
    return row.dia_limite if row else 23


def definir_dia_limite(dia_limite: int, coordenador: str) -> None:
    """Altera o dia-limite global. Só deve ser chamado pelo coordenador."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO configuracao_prazo_avaliacao (id, dia_limite, atualizado_em, atualizado_por)
                VALUES (1, :dia_limite, NOW(), :coordenador)
                ON CONFLICT (id) DO UPDATE
                SET dia_limite = EXCLUDED.dia_limite,
                    atualizado_em = NOW(),
                    atualizado_por = EXCLUDED.atualizado_por;
            """),
            {"dia_limite": dia_limite, "coordenador": coordenador},
        )


def data_limite_do_mes(mes_ref: date, dia_limite: int | None = None) -> date:
    """
    Retorna a data-limite para avaliar `mes_ref`.

    Prioridade:
      1) Se o coordenador definiu uma data específica para esse mês
         (via calendário, tabela prazos_avaliacao_mes), usa ela.
      2) Senão, calcula pelo dia-limite padrão (ex: dia 23 do mês
         seguinte ao mes_ref).
    """
    personalizado = obter_prazo_personalizado(mes_ref)
    if personalizado is not None:
        return personalizado

    if dia_limite is None:
        dia_limite = obter_dia_limite()

    ano = mes_ref.year if mes_ref.month < 12 else mes_ref.year + 1
    mes = mes_ref.month + 1 if mes_ref.month < 12 else 1

    import calendar
    ultimo_dia_do_mes = calendar.monthrange(ano, mes)[1]
    dia = min(dia_limite, ultimo_dia_do_mes)
    return date(ano, mes, dia)


def obter_prazo_personalizado(mes_ref: date) -> date | None:
    """Data-limite específica definida pelo coordenador (via calendário) para `mes_ref`, se houver."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT data_limite FROM prazos_avaliacao_mes
                WHERE mes_referencia = :mes_ref;
            """),
            {"mes_ref": mes_ref},
        ).fetchone()
    return row.data_limite if row else None


def definir_prazo_do_mes(mes_ref: date, data_limite: date, coordenador: str) -> None:
    """Coordenador escolhe (no calendário) a data-limite para avaliar `mes_ref`."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO prazos_avaliacao_mes (mes_referencia, data_limite, definido_por, atualizado_em)
                VALUES (:mes_ref, :data_limite, :coordenador, NOW())
                ON CONFLICT (mes_referencia) DO UPDATE
                SET data_limite = EXCLUDED.data_limite,
                    definido_por = EXCLUDED.definido_por,
                    atualizado_em = NOW();
            """),
            {"mes_ref": mes_ref, "data_limite": data_limite, "coordenador": coordenador},
        )


def prazo_do_mes_encerrado(mes_ref: date) -> bool:
    """True se hoje já passou da data-limite para avaliar `mes_ref`."""
    return date.today() > data_limite_do_mes(mes_ref)


def existe_autorizacao(supervisor: str, mes_ref: date) -> bool:
    """True se o coordenador já autorizou esse supervisor a avaliar `mes_ref` fora do prazo."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT 1 FROM autorizacoes_avaliacao_atrasada
                WHERE supervisor = :supervisor AND mes_referencia = :mes_ref;
            """),
            {"supervisor": supervisor, "mes_ref": mes_ref},
        ).fetchone()
    return row is not None


def autorizar_avaliacao_atrasada(supervisor: str, mes_ref: date, coordenador: str) -> None:
    """Coordenador libera esse supervisor para avaliar `mes_ref` mesmo fora do prazo."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO autorizacoes_avaliacao_atrasada (supervisor, mes_referencia, autorizado_por)
                VALUES (:supervisor, :mes_ref, :coordenador)
                ON CONFLICT (supervisor, mes_referencia) DO NOTHING;
            """),
            {"supervisor": supervisor, "mes_ref": mes_ref, "coordenador": coordenador},
        )


def revogar_autorizacao(supervisor: str, mes_ref: date) -> None:
    """Coordenador remove uma autorização já concedida (uso administrativo)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                DELETE FROM autorizacoes_avaliacao_atrasada
                WHERE supervisor = :supervisor AND mes_referencia = :mes_ref;
            """),
            {"supervisor": supervisor, "mes_ref": mes_ref},
        )


def mes_liberado_para_supervisor(supervisor: str, mes_ref: date) -> bool:
    """
    True se o supervisor pode lançar avaliações de `mes_ref` agora:
    dentro do prazo, OU fora do prazo mas com autorização do coordenador.
    """
    if not prazo_do_mes_encerrado(mes_ref):
        return True
    return existe_autorizacao(supervisor, mes_ref)


# ══════════════════════════════════════════════════════════
# SOLICITAÇÃO DE PRAZO
# O supervisor, ao esbarrar no prazo encerrado, pede ao coordenador
# para reabrir aquele mês. O coordenador vê o pedido e decide (autoriza
# esse supervisor, ou define uma nova data-limite para o mês inteiro).
# ══════════════════════════════════════════════════════════
def existe_solicitacao_pendente(supervisor: str, mes_ref: date) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT 1 FROM solicitacoes_prazo_avaliacao
                WHERE supervisor = :supervisor AND mes_referencia = :mes_ref AND status = 'pendente';
            """),
            {"supervisor": supervisor, "mes_ref": mes_ref},
        ).fetchone()
    return row is not None


def criar_solicitacao_prazo(supervisor: str, tecnico: str | None, mes_ref: date) -> None:
    """Registra o pedido do supervisor, se ainda não houver um pendente para o mesmo mês."""
    if existe_solicitacao_pendente(supervisor, mes_ref):
        return
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO solicitacoes_prazo_avaliacao (supervisor, tecnico, mes_referencia)
                VALUES (:supervisor, :tecnico, :mes_ref);
            """),
            {"supervisor": supervisor, "tecnico": tecnico, "mes_ref": mes_ref},
        )


def listar_solicitacoes_pendentes() -> list[dict]:
    """Todas as solicitações de prazo em aberto, mais recentes primeiro (para o coordenador)."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, supervisor, tecnico, mes_referencia, criado_em
                FROM solicitacoes_prazo_avaliacao
                WHERE status = 'pendente'
                ORDER BY criado_em DESC;
            """)
        ).fetchall()
    return [
        {
            "id": r.id,
            "supervisor": r.supervisor,
            "tecnico": r.tecnico,
            "mes_referencia": r.mes_referencia,
            "mes_referencia_label": r.mes_referencia.strftime("%m/%Y"),
            "mes_referencia_valor": r.mes_referencia.strftime("%Y-%m"),
            "criado_em": r.criado_em,
        }
        for r in rows
    ]


def marcar_solicitacoes_atendidas(supervisor: str, mes_ref: date, coordenador: str) -> None:
    """Marca como atendidas as solicitações pendentes daquele supervisor+mês (chamado ao autorizar)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE solicitacoes_prazo_avaliacao
                SET status = 'atendida', atendida_em = NOW(), atendida_por = :coordenador
                WHERE supervisor = :supervisor AND mes_referencia = :mes_ref AND status = 'pendente';
            """),
            {"supervisor": supervisor, "mes_ref": mes_ref, "coordenador": coordenador},
        )


def marcar_solicitacoes_atendidas_do_mes(mes_ref: date, coordenador: str) -> None:
    """Marca como atendidas TODAS as solicitações pendentes de um mês (usado ao mover a data-limite geral do mês)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE solicitacoes_prazo_avaliacao
                SET status = 'atendida', atendida_em = NOW(), atendida_por = :coordenador
                WHERE mes_referencia = :mes_ref AND status = 'pendente';
            """),
            {"mes_ref": mes_ref, "coordenador": coordenador},
        )


def recusar_solicitacao(solicitacao_id: int, coordenador: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE solicitacoes_prazo_avaliacao
                SET status = 'recusada', atendida_em = NOW(), atendida_por = :coordenador
                WHERE id = :id AND status = 'pendente';
            """),
            {"id": solicitacao_id, "coordenador": coordenador},
        )


def tecnicos_do_supervisor_no_mes(supervisor: str, mes_ref: date):
    """
    Técnicos deste supervisor pra fins de avaliação — baseado APENAS no
    vínculo ATIVO agora (tabela 'vinculo_tecnico'), sem olhar data alguma.
    O parâmetro mes_ref é mantido só por compatibilidade com quem chama
    esta função (o mês em si não interfere mais em quem aparece na lista):
    é sempre "quem está vinculado a este supervisor neste exato momento".
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT tecnico
                FROM vinculo_tecnico
                WHERE supervisor = :supervisor
                  AND data_desvinculacao IS NULL
                ORDER BY tecnico;
            """),
            {"supervisor": supervisor},
        ).fetchall()
    return [r.tecnico for r in rows]


def tecnicos_com_status_para_mes(supervisor: str, mes_ref: date):
    """
    Retorna a lista de técnicos do supervisor + se já foram avaliados
    NO MÊS ESCOLHIDO (mes_ref) — usado depois que o supervisor seleciona
    o mês/ano na tela inicial e entra na tela dos técnicos.

    IMPORTANTE: a lista é a UNIÃO de dois grupos —
      1) quem teve visita nesse mês com esse supervisor (pelas visitas)
      2) quem JÁ TEM avaliação lançada nesse mês por esse supervisor,
         mesmo sem visita dentro do próprio mês (ex: técnico avaliado
         que não visita há tempos, ou visita registrada com atraso)

    Isso evita que um técnico já avaliado "suma" da lista/ranking só
    porque a visita dele não caiu certinho dentro do mês.
    """
    tecnicos_do_mes = set(tecnicos_do_supervisor_no_mes(supervisor, mes_ref))

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, tecnico
                FROM avaliacoes_tecnicos
                WHERE supervisor = :supervisor AND mes_referencia = :mes_ref;
            """),
            {"supervisor": supervisor, "mes_ref": mes_ref},
        ).fetchall()
    avaliacao_id_por_tecnico = {r.tecnico: r.id for r in rows}

    tecnicos = sorted(tecnicos_do_mes | set(avaliacao_id_por_tecnico.keys()))

    return [
        {
            "tecnico": t,
            "avaliado": t in avaliacao_id_por_tecnico,
            "avaliacao_id": avaliacao_id_por_tecnico.get(t),
        }
        for t in tecnicos
    ]


def tecnicos_com_status_avaliacao(supervisor: str):
    """
    Mantido por compatibilidade: mesma coisa acima, mas sempre para o
    mês de referência atual (mês fechado mais recente).
    """
    mes_ref = mes_referencia_atual()
    return tecnicos_com_status_para_mes(supervisor, mes_ref), mes_ref


def avaliacoes_do_supervisor(supervisor: str):
    """
    Retorna todas as avaliações já feitas por este supervisor, mais recentes
    primeiro, agrupadas por mês de referência (para a tela "Minhas avaliações").

    Formato de retorno: lista de dicts
        [{"mes_referencia": date, "mes_label": "06/2026", "avaliacoes": [...]}, ...]
    cada avaliação dentro do grupo tem: id, tecnico, nota_final, data_avaliacao.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, tecnico, mes_referencia, nota_final, data_avaliacao
                FROM avaliacoes_tecnicos
                WHERE supervisor = :supervisor
                ORDER BY mes_referencia DESC, tecnico ASC;
            """),
            {"supervisor": supervisor},
        ).fetchall()

    grupos = []
    grupo_atual = None
    for r in rows:
        if grupo_atual is None or grupo_atual["mes_referencia"] != r.mes_referencia:
            grupo_atual = {
                "mes_referencia": r.mes_referencia,
                "mes_label": r.mes_referencia.strftime("%m/%Y"),
                "avaliacoes": [],
            }
            grupos.append(grupo_atual)
        grupo_atual["avaliacoes"].append({
            "id": r.id,
            "tecnico": r.tecnico,
            "nota_final": r.nota_final,
            "data_avaliacao": r.data_avaliacao,
        })
    return grupos


def avaliacoes_geral():
    """
    Retorna todas as avaliações já feitas por TODOS os supervisores, mais
    recentes primeiro, agrupadas por mês de referência (visão do coordenador
    geral na tela "Minhas avaliações").

    Formato de retorno: lista de dicts
        [{"mes_referencia": date, "mes_label": "06/2026", "avaliacoes": [...]}, ...]
    cada avaliação dentro do grupo tem: id, supervisor, tecnico, nota_final, data_avaliacao.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, supervisor, tecnico, mes_referencia, nota_final, data_avaliacao
                FROM avaliacoes_tecnicos
                ORDER BY mes_referencia DESC, supervisor ASC, tecnico ASC;
            """),
        ).fetchall()

    grupos = []
    grupo_atual = None
    for r in rows:
        if grupo_atual is None or grupo_atual["mes_referencia"] != r.mes_referencia:
            grupo_atual = {
                "mes_referencia": r.mes_referencia,
                "mes_label": r.mes_referencia.strftime("%m/%Y"),
                "avaliacoes": [],
            }
            grupos.append(grupo_atual)
        grupo_atual["avaliacoes"].append({
            "id": r.id,
            "supervisor": r.supervisor,
            "tecnico": r.tecnico,
            "nota_final": r.nota_final,
            "data_avaliacao": r.data_avaliacao,
        })
    return grupos


def buscar_avaliacao_por_id_admin(avaliacao_id: int):
    """
    Busca uma avaliação específica por id, SEM restringir por supervisor.
    Usado apenas pelo coordenador geral, que pode ver a avaliação de
    qualquer supervisor.
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM avaliacoes_tecnicos WHERE id = :id;"),
            {"id": avaliacao_id},
        ).mappings().fetchone()
    return dict(row) if row else None


def buscar_avaliacao_por_id(avaliacao_id: int, supervisor: str):
    """
    Busca uma avaliação específica, garantindo que ela pertence ao supervisor
    logado (evita que um supervisor veja avaliação de outro trocando o id na URL).
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT * FROM avaliacoes_tecnicos
                WHERE id = :id AND supervisor = :supervisor;
            """),
            {"id": avaliacao_id, "supervisor": supervisor},
        ).mappings().fetchone()
    return dict(row) if row else None


def avaliacoes_do_tecnico(supervisor: str, tecnico: str):
    """
    Busca todas as avaliações que este supervisor já fez para este técnico,
    da mais antiga para a mais recente (para a tela de comparação por mês).
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT * FROM avaliacoes_tecnicos
                WHERE supervisor = :supervisor AND tecnico = :tecnico
                ORDER BY mes_referencia ASC;
            """),
            {"supervisor": supervisor, "tecnico": tecnico},
        ).mappings().fetchall()
    return [dict(r) for r in rows]


def resumo_supervisores_para_mes(mes_ref: date):
    """
    Visão do coordenador: para cada supervisor, quantos técnicos ele tem,
    quantos já foram avaliados NO MÊS ESCOLHIDO (mes_ref), qual foi o
    melhor técnico dele nesse mês e a média do supervisor no mês.
    Também marca qual é o melhor supervisor do mês (maior média entre
    os que já têm pelo menos uma avaliação lançada).

    IMPORTANTE: o "total" de técnicos de cada supervisor vem do VÍNCULO
    MANUAL (tabela vinculo_tecnico) — quem o coordenador realmente
    associou àquele supervisor na tela de Vínculos/Associar técnicos —
    e não mais da visita automática (supervisor_atual). O processo aqui
    é manual: o coordenador escolhe o técnico e vincula ao supervisor;
    é essa associação que deve mandar na contagem, não quem aparece
    sozinho na base de visitas (que pode nem ter sido vinculado ainda).

    Considera vínculo ATIVO AGORA (data_desvinculacao IS NULL), igual ao
    resto do sistema (listar_tecnicos_do_supervisor) — sem exigir que
    data_inicio seja anterior ao mês avaliado. Isso é de propósito: como
    os vínculos estão sendo cadastrados manualmente agora (com
    data_inicio = hoje), exigir "já vinculado até o fim do mês avaliado"
    zerava o total de todo mundo sempre que o mês em avaliação (ex: 06/2026)
    fosse anterior à data em que o vínculo foi criado no sistema (hoje,
    07/2026) — mesmo o vínculo sendo válido.
    """
    engine = get_engine()

    with engine.connect() as conn:
        tecnicos_por_supervisor = conn.execute(
            text("""
                SELECT DISTINCT supervisor, tecnico
                FROM vinculo_tecnico
                WHERE data_desvinculacao IS NULL;
            """),
        ).fetchall()

        avaliados = conn.execute(
            text("""
                SELECT supervisor, tecnico, nota_final
                FROM avaliacoes_tecnicos
                WHERE mes_referencia = :mes_ref;
            """),
            {"mes_ref": mes_ref},
        ).fetchall()

    avaliados_por_supervisor = {}
    for r in avaliados:
        avaliados_por_supervisor.setdefault(r.supervisor, []).append(r)

    resumo = {}

    # União: quem está vinculado manualmente (fonte principal) + quem já
    # tem avaliação lançada nesse mês mas cujo vínculo não bateu certinho
    # dentro do período (evita que o técnico "suma" da contagem só por
    # isso, mesmo cuidado já tomado em tecnicos_com_status_para_mes).
    pares_vinculo = {(r.supervisor, r.tecnico) for r in tecnicos_por_supervisor}
    pares_avaliados = {(a.supervisor, a.tecnico) for a in avaliados}

    for supervisor, tecnico in (pares_vinculo | pares_avaliados):
        item = resumo.setdefault(supervisor, {"supervisor": supervisor, "total": 0, "avaliados": 0})
        item["total"] += 1
        if (supervisor, tecnico) in pares_avaliados:
            item["avaliados"] += 1

    for supervisor, item in resumo.items():
        registros = avaliados_por_supervisor.get(supervisor, [])
        if registros:
            melhor = max(registros, key=lambda a: (a.nota_final is not None, a.nota_final))
            item["melhor_tecnico"] = melhor.tecnico
            item["melhor_tecnico_media"] = melhor.nota_final
            medias_validas = [a.nota_final for a in registros if a.nota_final is not None]
            item["media_supervisor"] = (
                round(sum(medias_validas) / len(medias_validas), 2) if medias_validas else None
            )
        else:
            item["melhor_tecnico"] = None
            item["melhor_tecnico_media"] = None
            item["media_supervisor"] = None

    lista = sorted(resumo.values(), key=lambda x: x["supervisor"])
    for item in lista:
        item["pendentes"] = item["total"] - item["avaliados"]
        item["melhor_supervisor"] = False

    candidatos = [item for item in lista if item["media_supervisor"] is not None]
    if candidatos:
        melhor_item = max(candidatos, key=lambda x: x["media_supervisor"])
        melhor_item["melhor_supervisor"] = True

    return lista


def ranking_tecnicos_do_supervisor(supervisor: str, mes_ref: date):
    """
    Ranking (do 1º ao último) dos técnicos deste supervisor no mês escolhido,
    ordenado da maior para a menor nota final. Só entram técnicos já avaliados.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tecnico, nota_final
                FROM avaliacoes_tecnicos
                WHERE supervisor = :supervisor AND mes_referencia = :mes_ref
                ORDER BY nota_final DESC NULLS LAST, tecnico ASC;
            """),
            {"supervisor": supervisor, "mes_ref": mes_ref},
        ).fetchall()
    return [
        {"posicao": i + 1, "tecnico": r.tecnico, "nota_final": r.nota_final}
        for i, r in enumerate(rows)
    ]


def ranking_geral_tecnicos(mes_ref: date):
    """
    Ranking geral (de TODOS os supervisores) dos técnicos já avaliados no
    mês escolhido, do maior para o menor nota final — visão do coordenador.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT supervisor, tecnico, nota_final
                FROM avaliacoes_tecnicos
                WHERE mes_referencia = :mes_ref
                ORDER BY nota_final DESC NULLS LAST, tecnico ASC;
            """),
            {"mes_ref": mes_ref},
        ).fetchall()
    return [
        {"posicao": i + 1, "supervisor": r.supervisor, "tecnico": r.tecnico, "nota_final": r.nota_final}
        for i, r in enumerate(rows)
    ]


def ranking_supervisores(mes_ref: date):
    """
    Ranking dos supervisores no mês escolhido, do maior para o menor média
    (média das notas finais dos técnicos que cada um já avaliou). Só entram
    supervisores que já lançaram pelo menos uma avaliação no mês.
    """
    lista = resumo_supervisores_para_mes(mes_ref)
    candidatos = [item for item in lista if item["media_supervisor"] is not None]
    candidatos.sort(key=lambda x: x["media_supervisor"], reverse=True)
    for i, item in enumerate(candidatos):
        item["posicao"] = i + 1
    return candidatos


def melhor_tecnico_do_supervisor(supervisor: str, mes_ref: date):
    """
    Retorna o técnico com a maior média final entre os avaliados por este
    supervisor no mês escolhido, ou None se ele ainda não avaliou ninguém.
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT tecnico, nota_final
                FROM avaliacoes_tecnicos
                WHERE supervisor = :supervisor AND mes_referencia = :mes_ref
                ORDER BY nota_final DESC NULLS LAST, tecnico ASC
                LIMIT 1;
            """),
            {"supervisor": supervisor, "mes_ref": mes_ref},
        ).fetchone()
    if row is None:
        return None
    return {"tecnico": row.tecnico, "nota_final": row.nota_final}


def visao_geral_mes(mes_ref: date):
    """
    Consolida os números do painel inteligente do coordenador para o mês
    escolhido: totais, % de conclusão, média geral da rede e alertas
    (supervisores que ainda não lançaram nenhuma avaliação, ou com muitos
    pendentes).
    """
    engine = get_engine()
    with engine.connect() as conn:
        media_row = conn.execute(
            text("""
                SELECT AVG(nota_final) AS media
                FROM avaliacoes_tecnicos
                WHERE mes_referencia = :mes_ref;
            """),
            {"mes_ref": mes_ref},
        ).fetchone()

    resumo = resumo_supervisores_para_mes(mes_ref)
    total_tecnicos = sum(s["total"] for s in resumo)
    total_avaliados = sum(s["avaliados"] for s in resumo)
    total_pendentes = total_tecnicos - total_avaliados
    pct_conclusao = round(total_avaliados / total_tecnicos * 100, 1) if total_tecnicos else 0.0
    media_geral = round(float(media_row.media), 2) if media_row and media_row.media is not None else None

    nao_iniciados = [s for s in resumo if s["avaliados"] == 0 and s["total"] > 0]
    atencao = sorted(
        [s for s in resumo if s["pendentes"] > 0],
        key=lambda s: s["pendentes"],
        reverse=True,
    )

    return {
        "total_tecnicos": total_tecnicos,
        "total_avaliados": total_avaliados,
        "total_pendentes": total_pendentes,
        "pct_conclusao": pct_conclusao,
        "media_geral": media_geral,
        "nao_iniciados": nao_iniciados,
        "atencao": atencao,
    }


def avaliacoes_completas_mes(mes_ref: date, supervisor: str | None = None):
    """
    Retorna as avaliações completas (todas as colunas/respostas) do mês
    escolhido — usado na planilha de download com as respostas de cada
    pergunta, não só a média final. Se `supervisor` for informado, filtra
    só as dele; senão traz de todos (visão do coordenador).
    """
    engine = get_engine()
    query = "SELECT * FROM avaliacoes_tecnicos WHERE mes_referencia = :mes_ref"
    params = {"mes_ref": mes_ref}
    if supervisor:
        query += " AND supervisor = :supervisor"
        params["supervisor"] = supervisor
    query += " ORDER BY supervisor ASC, nota_final DESC NULLS LAST, tecnico ASC;"

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().fetchall()
    return [dict(r) for r in rows]


def dados_para_exportar(mes_ref: date, supervisor: str | None = None):
    """
    Retorna os dados básicos para a planilha de download: supervisor, técnico,
    média final e mês de referência. Se `supervisor` for informado, filtra
    só as avaliações daquele supervisor; senão traz de todos (visão do
    coordenador). Só entram técnicos já avaliados no mês (quem tem nota).
    """
    engine = get_engine()
    query = """
        SELECT supervisor, tecnico, nota_final, mes_referencia
        FROM avaliacoes_tecnicos
        WHERE mes_referencia = :mes_ref
    """
    params = {"mes_ref": mes_ref}
    if supervisor:
        query += " AND supervisor = :supervisor"
        params["supervisor"] = supervisor
    query += " ORDER BY supervisor ASC, nota_final DESC NULLS LAST, tecnico ASC;"

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).fetchall()
    return rows


def resumo_geral_supervisores():
    """Mantido por compatibilidade: mesma coisa acima, mas para o mês atual."""
    mes_ref = mes_referencia_atual()
    return resumo_supervisores_para_mes(mes_ref), mes_ref


def tecnicos_com_avaliacao_para_mes(supervisor: str, mes_ref: date):
    """
    Como tecnicos_com_status_para_mes, mas também traz o id e a média final
    da avaliação (quando existe) — usado na tela do coordenador para linkar
    direto para o detalhe da avaliação de cada técnico.
    """
    tecnicos_do_mes = set(tecnicos_do_supervisor_no_mes(supervisor, mes_ref))

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, tecnico, nota_final
                FROM avaliacoes_tecnicos
                WHERE supervisor = :supervisor AND mes_referencia = :mes_ref;
            """),
            {"supervisor": supervisor, "mes_ref": mes_ref},
        ).fetchall()
    avaliacoes_por_tecnico = {r.tecnico: r for r in rows}

    tecnicos = sorted(tecnicos_do_mes | set(avaliacoes_por_tecnico.keys()))

    resultado = []
    melhor_media = None
    for t in tecnicos:
        av = avaliacoes_por_tecnico.get(t)
        media = av.nota_final if av else None
        if media is not None and (melhor_media is None or media > melhor_media):
            melhor_media = media
        resultado.append({
            "tecnico": t,
            "avaliado": av is not None,
            "avaliacao_id": av.id if av else None,
            "nota_final": media,
        })

    for item in resultado:
        item["melhor"] = melhor_media is not None and item["nota_final"] == melhor_media

    # Ordena do melhor para o pior (maior média primeiro); quem ainda não foi
    # avaliado (pendente) vai para o final, em ordem alfabética.
    resultado.sort(key=lambda item: (
        item["nota_final"] is None,
        -(item["nota_final"] or 0),
        item["tecnico"],
    ))

    for i, item in enumerate(resultado):
        item["posicao"] = i + 1 if item["nota_final"] is not None else None

    return resultado


# ══════════════════════════════════════════════════════════
# RANKING OBJETIVO (baseado em visitas) — portado do app Streamlit
# de ranking ATeG. Nota de 0 a 1, calculada a partir de 7 indicadores
# de mesmo peso (propriedades ativas, total de visitas, orientações,
# taxa de validade, taxa de orientações concluídas, propriedades
# inativas e sobreposição de projetos), normalizados e comparados
# dentro do grupo do supervisor.
#
# É INDEPENDENTE da avaliação subjetiva (as 25 perguntas) — mostrado
# lado a lado, sem se misturar num número só.
# ══════════════════════════════════════════════════════════
QUERY_RANKING_OBJETIVO = """
WITH Parametros AS (
    SELECT :dt_inicio AS dt_inicio, :dt_fim AS dt_fim
),
HistoricoCompletoProjetos AS (
    SELECT tecnico_responsavel, id_propriedade,
           COUNT(DISTINCT id_projeto) AS total_projetos_por_propriedade
    FROM public.acompanhamento_mensal_visitas
    GROUP BY tecnico_responsavel, id_propriedade
),
PropriedadesSobrepostasGlobal AS (
    SELECT tecnico_responsavel,
           COUNT(DISTINCT id_propriedade) AS total_propriedades_com_multiplos_projetos
    FROM HistoricoCompletoProjetos
    WHERE total_projetos_por_propriedade > 1
    GROUP BY tecnico_responsavel
),
UltimoSupervisorPorTecnico AS (
    SELECT DISTINCT ON (tecnico_responsavel) tecnico_responsavel, supervisor_atual AS ultimo_supervisor
    FROM public.acompanhamento_mensal_visitas
    WHERE dt_visita BETWEEN (SELECT dt_inicio FROM Parametros) AND (SELECT dt_fim FROM Parametros)
    ORDER BY tecnico_responsavel, dt_visita DESC
),
UltimoProjetoPorTecnico AS (
    SELECT DISTINCT ON (tecnico_responsavel) tecnico_responsavel, projeto AS ultimo_projeto
    FROM public.acompanhamento_mensal_visitas
    WHERE dt_visita BETWEEN (SELECT dt_inicio FROM Parametros) AND (SELECT dt_fim FROM Parametros)
      AND projeto IS NOT NULL
    ORDER BY tecnico_responsavel, dt_visita DESC
),
UltimaAtividadePorTecnico AS (
    SELECT DISTINCT ON (tecnico_responsavel) tecnico_responsavel, atividade AS ultima_atividade
    FROM public.acompanhamento_mensal_visitas
    WHERE dt_visita BETWEEN (SELECT dt_inicio FROM Parametros) AND (SELECT dt_fim FROM Parametros)
      AND atividade IS NOT NULL
    ORDER BY tecnico_responsavel, dt_visita DESC
),
ResumoTecnicos AS (
    SELECT
        tecnico_responsavel,
        COUNT(DISTINCT CASE WHEN vinculo_status = 'ATIVA'   THEN id_propriedade END) AS propriedades_ativas,
        COUNT(DISTINCT CASE WHEN vinculo_status = 'INATIVA' THEN id_propriedade END) AS propriedades_inativas,
        COUNT(*) AS total_de_visitas,
        COUNT(CASE WHEN visita_presencial = 'SIM' THEN 1 END) AS total_visitas_presenciais,
        COUNT(CASE WHEN visita_valida = 'Valida' AND visita_presencial = 'SIM' THEN 1 END) AS total_visitas_validas,
        SUM(COALESCE(ori_total_geral, 0)) AS total_orientacoes_geral,
        SUM(COALESCE(ori_concluida, 0)) AS total_orientacoes_concluidas
    FROM public.acompanhamento_mensal_visitas
    WHERE dt_visita BETWEEN (SELECT dt_inicio FROM Parametros) AND (SELECT dt_fim FROM Parametros)
    GROUP BY tecnico_responsavel
),
Taxas AS (
    SELECT
        r.tecnico_responsavel, r.propriedades_ativas, r.propriedades_inativas,
        r.total_de_visitas, r.total_visitas_presenciais, r.total_visitas_validas,
        r.total_orientacoes_geral, r.total_orientacoes_concluidas,
        CASE WHEN r.total_de_visitas > 0 THEN r.total_visitas_validas::NUMERIC / r.total_de_visitas ELSE 0 END AS taxa_validade,
        CASE WHEN r.total_orientacoes_geral > 0 THEN r.total_orientacoes_concluidas::NUMERIC / r.total_orientacoes_geral ELSE 0 END AS taxa_ori_concluidas,
        COALESCE(p.total_propriedades_com_multiplos_projetos, 0) AS qtd_multiplos_projetos
    FROM ResumoTecnicos r
    LEFT JOIN PropriedadesSobrepostasGlobal p ON r.tecnico_responsavel = p.tecnico_responsavel
    WHERE r.propriedades_ativas > 0
),
Normalizado AS (
    SELECT
        t.tecnico_responsavel, s.ultimo_supervisor, pr.ultimo_projeto, at.ultima_atividade,
        t.propriedades_ativas, t.propriedades_inativas, t.total_de_visitas,
        t.total_visitas_presenciais, t.total_visitas_validas,
        t.total_orientacoes_geral, t.total_orientacoes_concluidas, t.qtd_multiplos_projetos,
        ROUND(t.taxa_validade * 100, 1) AS pct_visitas_validas,
        ROUND(t.taxa_ori_concluidas * 100, 1) AS pct_ori_concluidas,
        COALESCE((t.propriedades_ativas - MIN(t.propriedades_ativas) OVER w)::NUMERIC
            / NULLIF(MAX(t.propriedades_ativas) OVER w - MIN(t.propriedades_ativas) OVER w, 0), 1.0) AS n_prop_ativas,
        COALESCE((t.total_visitas_presenciais - MIN(t.total_visitas_presenciais) OVER w)::NUMERIC
            / NULLIF(MAX(t.total_visitas_presenciais) OVER w - MIN(t.total_visitas_presenciais) OVER w, 0), 1.0) AS n_total_visitas,
        COALESCE((t.total_orientacoes_geral - MIN(t.total_orientacoes_geral) OVER w)::NUMERIC
            / NULLIF(MAX(t.total_orientacoes_geral) OVER w - MIN(t.total_orientacoes_geral) OVER w, 0), 1.0) AS n_ori_geral,
        COALESCE((t.taxa_validade - MIN(t.taxa_validade) OVER w)
            / NULLIF(MAX(t.taxa_validade) OVER w - MIN(t.taxa_validade) OVER w, 0), 1.0) AS n_taxa_validade,
        COALESCE((t.taxa_ori_concluidas - MIN(t.taxa_ori_concluidas) OVER w)
            / NULLIF(MAX(t.taxa_ori_concluidas) OVER w - MIN(t.taxa_ori_concluidas) OVER w, 0), 1.0) AS n_taxa_ori_concluidas,
        1.0 - COALESCE((t.propriedades_inativas - MIN(t.propriedades_inativas) OVER w)::NUMERIC
            / NULLIF(MAX(t.propriedades_inativas) OVER w - MIN(t.propriedades_inativas) OVER w, 0), 0.0) AS n_prop_inativas,
        1.0 - COALESCE((t.qtd_multiplos_projetos - MIN(t.qtd_multiplos_projetos) OVER w)::NUMERIC
            / NULLIF(MAX(t.qtd_multiplos_projetos) OVER w - MIN(t.qtd_multiplos_projetos) OVER w, 0), 0.0) AS n_multi_projetos
    FROM Taxas t
    LEFT JOIN UltimoSupervisorPorTecnico s ON t.tecnico_responsavel = s.tecnico_responsavel
    LEFT JOIN UltimoProjetoPorTecnico pr ON t.tecnico_responsavel = pr.tecnico_responsavel
    LEFT JOIN UltimaAtividadePorTecnico at ON t.tecnico_responsavel = at.tecnico_responsavel
    WINDOW w AS (ORDER BY t.tecnico_responsavel ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
)
SELECT
    tecnico_responsavel, ultimo_supervisor, ultimo_projeto, ultima_atividade,
    propriedades_ativas, propriedades_inativas, total_de_visitas,
    total_visitas_presenciais, total_visitas_validas,
    total_orientacoes_geral, total_orientacoes_concluidas, qtd_multiplos_projetos,
    pct_visitas_validas, pct_ori_concluidas,
    ROUND(CAST(n_prop_ativas         AS NUMERIC), 4) AS n_prop_ativas,
    ROUND(CAST(n_total_visitas       AS NUMERIC), 4) AS n_total_visitas,
    ROUND(CAST(n_ori_geral           AS NUMERIC), 4) AS n_ori_geral,
    ROUND(CAST(n_taxa_validade       AS NUMERIC), 4) AS n_taxa_validade,
    ROUND(CAST(n_taxa_ori_concluidas AS NUMERIC), 4) AS n_taxa_ori_concluidas,
    ROUND(CAST(n_prop_inativas       AS NUMERIC), 4) AS n_prop_inativas,
    ROUND(CAST(n_multi_projetos      AS NUMERIC), 4) AS n_multi_projetos,
    ROUND(
        CAST(
            CASE WHEN qtd_multiplos_projetos > 0 THEN
                ((COALESCE(n_prop_ativas,0)+COALESCE(n_total_visitas,0)+COALESCE(n_ori_geral,0)
                  +COALESCE(n_taxa_validade,0)+COALESCE(n_taxa_ori_concluidas,0)
                  +COALESCE(n_prop_inativas,0)+COALESCE(n_multi_projetos,0)) / 7.0) * 0.5
            ELSE
                (COALESCE(n_prop_ativas,0)+COALESCE(n_total_visitas,0)+COALESCE(n_ori_geral,0)
                 +COALESCE(n_taxa_validade,0)+COALESCE(n_taxa_ori_concluidas,0)
                 +COALESCE(n_prop_inativas,0)+COALESCE(n_multi_projetos,0)) / 7.0
            END
        AS NUMERIC), 4
    ) AS nota_objetiva,
    DENSE_RANK() OVER (
        PARTITION BY ultimo_supervisor
        ORDER BY CASE WHEN qtd_multiplos_projetos > 0 THEN
                ((COALESCE(n_prop_ativas,0)+COALESCE(n_total_visitas,0)+COALESCE(n_ori_geral,0)
                  +COALESCE(n_taxa_validade,0)+COALESCE(n_taxa_ori_concluidas,0)
                  +COALESCE(n_prop_inativas,0)+COALESCE(n_multi_projetos,0)) / 7.0) * 0.5
            ELSE
                (COALESCE(n_prop_ativas,0)+COALESCE(n_total_visitas,0)+COALESCE(n_ori_geral,0)
                 +COALESCE(n_taxa_validade,0)+COALESCE(n_taxa_ori_concluidas,0)
                 +COALESCE(n_prop_inativas,0)+COALESCE(n_multi_projetos,0)) / 7.0
            END DESC
    ) AS pos,
    DENSE_RANK() OVER (
        PARTITION BY ultimo_projeto
        ORDER BY (
            COALESCE(n_prop_ativas,0)+COALESCE(n_total_visitas,0)+COALESCE(n_ori_geral,0)
            +COALESCE(n_taxa_validade,0)+COALESCE(n_taxa_ori_concluidas,0)
            +COALESCE(n_prop_inativas,0)+COALESCE(n_multi_projetos,0)
        ) DESC
    ) AS pos_projeto,
    DENSE_RANK() OVER (
        PARTITION BY ultima_atividade
        ORDER BY (
            COALESCE(n_prop_ativas,0)+COALESCE(n_total_visitas,0)+COALESCE(n_ori_geral,0)
            +COALESCE(n_taxa_validade,0)+COALESCE(n_taxa_ori_concluidas,0)
            +COALESCE(n_prop_inativas,0)+COALESCE(n_multi_projetos,0)
        ) DESC
    ) AS pos_atividade
FROM Normalizado
ORDER BY ultimo_supervisor, pos;
"""


def ranking_objetivo_tecnicos(dt_inicio: date, dt_fim: date) -> list[dict]:
    """
    Ranking objetivo dos técnicos no período (baseado nas visitas), com
    nota de 0 a 1 — independente da avaliação subjetiva (25 perguntas).
    Portado do app de ranking ATeG (Streamlit) que já existia.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(QUERY_RANKING_OBJETIVO),
            {"dt_inicio": dt_inicio, "dt_fim": dt_fim},
        ).mappings().fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════
# CADASTRO (fundido de repositorio_cadastros.py)
#
# Diferente do resto deste arquivo (que lida com avaliação/visitas),
# esta seção cuida do CADASTRO em si:
# - Supervisor: inserido manualmente pelo coordenador.
# - Técnico: sincronizado automaticamente da tabela de visitas (por ID),
#   com dados cadastrais complementares preenchidos pelo coordenador.
# ══════════════════════════════════════════════════════════

# Motivos padronizados de desativação de supervisor (mesmo esquema usado
# no desvínculo de técnico: lista fixa + "Outro" com descrição livre).
MOTIVOS_DESATIVACAO_SUPERVISOR = [
    "Saiu da empresa",
    "Trocou de função",
    "Encerramento de contrato",
    "Licença/afastamento",
]

# Motivos padronizados de desativação de TÉCNICO (cadastro mestre, tabela
# 'tecnicos') — lista fechada, sem "Outro" com texto livre igual às outras.
MOTIVOS_DESATIVACAO_TECNICO = [
    "Fim de Contrato",
    "Distrato",
    "Distrato/Descredenciamento",
]


# ══════════════════════════════════════════════════════════
# SUPERVISORES
# ══════════════════════════════════════════════════════════
def sincronizar_supervisores_de_usuarios():
    """
    Popula/atualiza a tabela 'supervisores' a partir de quem já tem login
    em usuarios_supervisores (só os do tipo 'supervisor', não o coordenador).
    Assim aproveita os nomes já corretos e usados de verdade no sistema,
    sem precisar reimportar de planilha.
    """
    engine = get_engine()
    with engine.begin() as conn:
        resultado = conn.execute(
            text("""
                INSERT INTO supervisores (nome)
                SELECT supervisor FROM usuarios_supervisores WHERE tipo = 'supervisor'
                ON CONFLICT (nome) DO NOTHING
                RETURNING nome;
            """)
        ).fetchall()
    return [r.nome for r in resultado]


def listar_supervisores_cadastrados(apenas_ativos: bool = False):
    engine = get_engine()
    query = "SELECT * FROM supervisores"
    if apenas_ativos:
        query += " WHERE ativo = TRUE"
    query += " ORDER BY nome;"
    with engine.connect() as conn:
        linhas = conn.execute(text(query)).mappings().all()
    return [dict(l) for l in linhas]


def criar_supervisor(
    nome: str,
    rg: str = None,
    cpf: str = None,
    contato: str = None,
    empresa: str = None,
    cnpj_empresa: str = None,
    data_inicio_vinculo=None,
    data_fim_vinculo=None,
):
    """Insere um supervisor novo manualmente, já com os dados cadastrais
    completos (se informados). Só o coordenador pode chamar isso."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO supervisores
                    (nome, rg, cpf, contato, empresa, cnpj_empresa, data_inicio_vinculo, data_fim_vinculo)
                VALUES
                    (:nome, :rg, :cpf, :contato, :empresa, :cnpj_empresa, :data_inicio_vinculo, :data_fim_vinculo)
                ON CONFLICT (nome) DO NOTHING;
            """),
            {
                "nome": nome.strip(),
                "rg": rg or None,
                "cpf": cpf or None,
                "contato": contato or None,
                "empresa": empresa or None,
                "cnpj_empresa": cnpj_empresa or None,
                "data_inicio_vinculo": data_inicio_vinculo or None,
                "data_fim_vinculo": data_fim_vinculo or None,
            },
        )


def definir_ativo_supervisor(supervisor_id: int, ativo: bool, motivo_desativacao: str = None):
    """
    Ativa/desativa um supervisor. Só o coordenador pode chamar isso.
    Ao desativar, grava o motivo e a data (igual ao desvínculo de técnico).
    Ao reativar, limpa motivo e data — não faz sentido carregar o motivo
    de uma desativação antiga pra frente.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE supervisores
                SET ativo = :ativo,
                    motivo_desativacao = :motivo_desativacao,
                    data_desativacao = :data_desativacao,
                    atualizado_em = NOW()
                WHERE id = :id;
            """),
            {
                "id": supervisor_id,
                "ativo": ativo,
                "motivo_desativacao": None if ativo else motivo_desativacao,
                "data_desativacao": None if ativo else date.today(),
            },
        )


def obter_supervisor(supervisor_id: int):
    engine = get_engine()
    with engine.connect() as conn:
        linha = conn.execute(
            text("SELECT * FROM supervisores WHERE id = :id;"), {"id": supervisor_id}
        ).mappings().first()
    return dict(linha) if linha else None


def atualizar_dados_cadastrais_supervisor(
    supervisor_id: int,
    rg: str = None,
    cpf: str = None,
    contato: str = None,
    empresa: str = None,
    cnpj_empresa: str = None,
    data_inicio_vinculo=None,
    data_fim_vinculo=None,
):
    """Preenche/atualiza os dados complementares do supervisor (RG, CPF, contato, empresa, CNPJ, vínculo)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE supervisores
                SET rg = :rg, cpf = :cpf, contato = :contato,
                    empresa = :empresa, cnpj_empresa = :cnpj_empresa,
                    data_inicio_vinculo = :data_inicio_vinculo,
                    data_fim_vinculo = :data_fim_vinculo,
                    atualizado_em = NOW()
                WHERE id = :id;
            """),
            {
                "id": supervisor_id,
                "rg": rg or None,
                "cpf": cpf or None,
                "contato": contato or None,
                "empresa": empresa or None,
                "cnpj_empresa": cnpj_empresa or None,
                "data_inicio_vinculo": data_inicio_vinculo or None,
                "data_fim_vinculo": data_fim_vinculo or None,
            },
        )


def listar_projetos_do_supervisor(nome_supervisor: str):
    """
    Lista os projetos (distintos) dos técnicos atualmente vinculados a
    esse supervisor — não é um campo digitado, vem automático a partir
    dos técnicos dele (tecnico_atividades), cruzando por ID.
    """
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(
            text("""
                SELECT DISTINCT ta.projeto
                FROM vinculo_tecnico v
                JOIN tecnicos t ON lower(trim(regexp_replace(t.nome, '\\s+', ' ', 'g'))) = lower(trim(regexp_replace(v.tecnico, '\\s+', ' ', 'g')))
                JOIN tecnico_atividades ta ON ta.id_tecnico_responsavel = t.id_tecnico_responsavel
                WHERE v.supervisor = :supervisor
                  AND v.data_desvinculacao IS NULL
                  AND ta.projeto IS NOT NULL
                ORDER BY ta.projeto;
            """),
            {"supervisor": nome_supervisor},
        ).fetchall()
    return [r.projeto for r in linhas]


def contar_tecnicos_vinculados(nome_supervisor: str) -> int:
    """Quantos técnicos estão HOJE vinculados (ativos) a esse supervisor.
    Usado pra decidir se dá pra excluir o cadastro dele ou não."""
    engine = get_engine()
    with engine.connect() as conn:
        total = conn.execute(
            text("""
                SELECT COUNT(*) FROM vinculo_tecnico
                WHERE supervisor = :supervisor
                  AND data_desvinculacao IS NULL;
            """),
            {"supervisor": nome_supervisor},
        ).scalar()
    return total or 0


def excluir_supervisor(supervisor_id: int, nome_supervisor: str):
    """Exclui o cadastro do supervisor. Se ele ainda tiver técnico(s)
    vinculado(s), apaga esses vínculos da tabela vinculo_tecnico primeiro
    (não bloqueia mais a exclusão por causa disso)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM vinculo_tecnico WHERE supervisor = :supervisor;"),
            {"supervisor": nome_supervisor},
        )
        conn.execute(
            text("DELETE FROM supervisores WHERE id = :id;"),
            {"id": supervisor_id},
        )


# ══════════════════════════════════════════════════════════
# TÉCNICOS (cadastro mestre — identidade + dados complementares)
# ══════════════════════════════════════════════════════════
def listar_relatorio_completo_tecnicos(supervisor: str | None = None):
    """
    Relatório geral: TODO técnico cadastrado (ativo ou não), com os dados
    cadastrais completos e a situação atual resumida em uma única string,
    pronta pra exibir/imprimir/exportar:
      - "Desativado"                    → ativo = FALSE na tabela tecnicos
      - "Vinculado a {supervisor}"       → ativo = TRUE e tem vínculo aberto
      - "Descredenciado (sem supervisor)"→ ativo = TRUE, já teve vínculo,
                                            mas não tem nenhum aberto agora
      - "Sem vínculo (nunca associado)"  → ativo = TRUE e nunca teve vínculo

    Também separa a "Avaliação do Técnico" do motivo de desativação: o
    formulário de desativar grava tudo junto numa string só, no formato
    "{motivo} — Avaliação do Técnico: {texto}" — aqui isso vira dois
    campos: motivo_desativacao_curto (só o motivo) e avaliacao_desativacao
    (só o texto da avaliação, quando existir).

    `supervisor`: se informado, só traz técnicos com vínculo ATIVO com
    esse supervisor (não filtra desativados/descredenciados/sem vínculo,
    já que esses não têm supervisor atual nenhum).
    """
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(
            text("""
                SELECT
                    t.id_tecnico_responsavel, t.nome, t.rg, t.cpf, t.contato,
                    t.email, t.endereco, t.municipio, t.empresa, t.cnpj_empresa,
                    t.mes_ano_capacitacao_metodologica, t.modalidade_capacitacao_metodologica,
                    t.ativo, t.motivo_desativacao, t.data_desativacao,
                    atual.supervisor AS supervisor_atual,
                    COALESCE(cad.projeto, atual.projeto) AS projeto_atual,
                    COALESCE(cad.atividade, atual.atividade) AS atividade_atual,
                    EXISTS (
                        SELECT 1 FROM vinculo_tecnico v WHERE v.tecnico = t.nome
                    ) AS ja_teve_vinculo
                FROM tecnicos t
                LEFT JOIN vinculo_tecnico atual
                    ON atual.tecnico = t.nome AND atual.data_desvinculacao IS NULL
                LEFT JOIN LATERAL (
                    SELECT ta.projeto, ta.atividade
                    FROM tecnico_atividades ta
                    WHERE ta.id_tecnico_responsavel = t.id_tecnico_responsavel
                    ORDER BY ta.ultima_visita DESC NULLS LAST
                    LIMIT 1
                ) cad ON true
                ORDER BY t.nome;
            """)
        ).mappings().all()

    marcador = " — Avaliação do Técnico: "
    resultado = []
    for l in linhas:
        d = dict(l)
        if not d["ativo"]:
            d["situacao"] = "Desativado"
        elif d["supervisor_atual"]:
            d["situacao"] = f"Vinculado a {d['supervisor_atual']}"
        elif d["ja_teve_vinculo"]:
            d["situacao"] = "Descredenciado (sem supervisor)"
        else:
            d["situacao"] = "Sem vínculo (nunca associado)"

        motivo_bruto = d["motivo_desativacao"] or ""
        if marcador in motivo_bruto:
            motivo_curto, avaliacao = motivo_bruto.split(marcador, 1)
        else:
            motivo_curto, avaliacao = motivo_bruto, ""
        d["motivo_desativacao_curto"] = motivo_curto or None
        d["avaliacao_desativacao"] = avaliacao or None

        if supervisor and d["supervisor_atual"] != supervisor:
            continue
        resultado.append(d)
    return resultado


def listar_tecnicos_cadastrados(apenas_ativos: bool = False):
    engine = get_engine()
    query = "SELECT * FROM tecnicos"
    if apenas_ativos:
        query += " WHERE ativo = TRUE"
    query += " ORDER BY nome;"
    with engine.connect() as conn:
        linhas = conn.execute(text(query)).mappings().all()
    return [dict(l) for l in linhas]


def obter_tecnico(id_tecnico_responsavel: int):
    engine = get_engine()
    with engine.connect() as conn:
        linha = conn.execute(
            text("SELECT * FROM tecnicos WHERE id_tecnico_responsavel = :id;"),
            {"id": id_tecnico_responsavel},
        ).mappings().first()
    return dict(linha) if linha else None


def obter_tecnico_por_nome(nome: str):
    """
    Busca o cadastro mestre do técnico (tabela 'tecnicos') pelo nome,
    usando comparação normalizada (ignora acento/maiúscula/espaço extra)
    pra não falhar por causa de pequenas diferenças de digitação/URL.
    Retorna o dict com TODAS as colunas (rg, cpf, contato, email, empresa,
    cnpj_empresa, endereco, municipio, datas de vínculo etc.) ou None se
    esse técnico ainda não tiver registro nenhum na tabela mestra.
    """
    alvo = normalizar(nome)
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(text("SELECT * FROM tecnicos;")).mappings().all()
    for linha in linhas:
        if normalizar(linha["nome"]) == alvo:
            return dict(linha)
    return None


def listar_tecnicos_desativados():
    """
    Técnicos com ativo = FALSE na tabela mestra 'tecnicos' — foram
    desativados pelo coordenador (motivo/data registrados em
    motivo_desativacao/data_desativacao).
    """
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(
            text("""
                SELECT * FROM tecnicos
                WHERE ativo = FALSE
                ORDER BY data_desativacao DESC NULLS LAST, nome;
            """)
        ).mappings().all()
    return [dict(l) for l in linhas]


def listar_tecnicos_descredenciados():
    """
    Técnicos ATIVOS na tabela mestra que JÁ TIVERAM vínculo com algum
    supervisor (existe pelo menos uma linha deles em vinculo_tecnico) mas
    não têm nenhum vínculo aberto agora — ou seja, foram REALMENTE
    desvinculados em algum momento. Técnico que nunca teve vínculo
    nenhum (nunca foi associado a um supervisor) NÃO entra aqui — esse
    caso é só "ainda não vinculado", não "descredenciado".
    Traz junto o motivo/data/supervisor do desvínculo mais recente.
    """
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(
            text("""
                SELECT t.*,
                       (SELECT v.motivo_desvinculacao FROM vinculo_tecnico v
                        WHERE v.tecnico = t.nome AND v.data_desvinculacao IS NOT NULL
                        ORDER BY v.data_desvinculacao DESC LIMIT 1) AS motivo_desvinculacao,
                       (SELECT v.data_desvinculacao FROM vinculo_tecnico v
                        WHERE v.tecnico = t.nome AND v.data_desvinculacao IS NOT NULL
                        ORDER BY v.data_desvinculacao DESC LIMIT 1) AS data_desvinculacao,
                       (SELECT v.supervisor FROM vinculo_tecnico v
                        WHERE v.tecnico = t.nome AND v.data_desvinculacao IS NOT NULL
                        ORDER BY v.data_desvinculacao DESC LIMIT 1) AS ultimo_supervisor
                FROM tecnicos t
                WHERE t.ativo = TRUE
                  AND EXISTS (
                      SELECT 1 FROM vinculo_tecnico v WHERE v.tecnico = t.nome
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM vinculo_tecnico v
                      WHERE v.tecnico = t.nome AND v.data_desvinculacao IS NULL
                  )
                ORDER BY data_desvinculacao DESC NULLS LAST, t.nome;
            """)
        ).mappings().all()
    return [dict(l) for l in linhas]


def definir_ativo_tecnico(id_tecnico_responsavel: int, ativo: bool, motivo_desativacao: str = None):
    """
    Ativa/desativa um técnico. Só o coordenador pode chamar isso.
    Ao desativar, grava o motivo e a data de hoje; ao reativar, limpa os dois
    (igual ao esquema já usado pra supervisor).
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE tecnicos
                SET ativo = :ativo,
                    motivo_desativacao = :motivo_desativacao,
                    data_desativacao = :data_desativacao,
                    atualizado_em = NOW()
                WHERE id_tecnico_responsavel = :id;
            """),
            {
                "id": id_tecnico_responsavel,
                "ativo": ativo,
                "motivo_desativacao": None if ativo else motivo_desativacao,
                "data_desativacao": None if ativo else date.today(),
            },
        )


def atualizar_dados_cadastrais_tecnico(
    id_tecnico_responsavel: int,
    rg: str = None,
    cpf: str = None,
    contato: str = None,
    email: str = None,
    empresa: str = None,
    cnpj_empresa: str = None,
    endereco: str = None,
    municipio: str = None,
    data_inicio_vinculo=None,
    data_fim_vinculo=None,
    mes_ano_capacitacao_metodologica=None,
    modalidade_capacitacao_metodologica: str = None,
):
    """
    Preenche/atualiza os dados complementares do técnico (RG, CPF, contato,
    email, empresa, CNPJ, endereço, município, datas de vínculo, mês/ano e
    modalidade da capacitação metodológica). O nome, primeira/última visita
    continuam vindo só da sincronização com a tabela de visitas — esses
    aqui são só os campos "extras" que o supervisor/coordenador digita.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE tecnicos
                SET rg = :rg, cpf = :cpf, contato = :contato, email = :email,
                    empresa = :empresa, cnpj_empresa = :cnpj_empresa,
                    endereco = :endereco, municipio = :municipio,
                    data_inicio_vinculo = :data_inicio_vinculo,
                    data_fim_vinculo = :data_fim_vinculo,
                    mes_ano_capacitacao_metodologica = :mes_ano_capacitacao_metodologica,
                    modalidade_capacitacao_metodologica = :modalidade_capacitacao_metodologica,
                    atualizado_em = NOW()
                WHERE id_tecnico_responsavel = :id;
            """),
            {
                "id": id_tecnico_responsavel,
                "rg": rg or None,
                "cpf": cpf or None,
                "contato": contato or None,
                "email": email or None,
                "empresa": empresa or None,
                "cnpj_empresa": cnpj_empresa or None,
                "endereco": endereco or None,
                "municipio": municipio or None,
                "data_inicio_vinculo": data_inicio_vinculo or None,
                "data_fim_vinculo": data_fim_vinculo or None,
                "mes_ano_capacitacao_metodologica": mes_ano_capacitacao_metodologica or None,
                "modalidade_capacitacao_metodologica": modalidade_capacitacao_metodologica or None,
            },
        )


def sincronizar_tecnicos_da_visita():
    """
    Atualiza (ou cria) os técnicos na tabela mestra a partir de TODO o
    histórico de visitas até hoje (sem precisar escolher período — pega
    tudo de uma vez). Segue o mesmo filtro da consulta de auditoria usada
    pelo coordenador: só considera visita com flg_coleta_dados = 'Não'.
    Não mexe nos dados cadastrais complementares (CPF, empresa etc.),
    só nome/primeira/última visita.
    """
    engine = get_engine()
    query = """
        SELECT
            id_tecnico_responsavel,
            tecnico_responsavel,
            MIN(dt_visita_v::date) AS primeira_visita,
            MAX(dt_visita_v::date) AS ultima_visita
        FROM public.acompanhamento_mensal_visitas
        WHERE dt_visita_v::date <= CURRENT_DATE
          AND flg_coleta_dados = 'Não'
          AND id_tecnico_responsavel IS NOT NULL
        GROUP BY id_tecnico_responsavel, tecnico_responsavel;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query)).mappings().all()

    processados = 0
    with engine.begin() as conn:
        for l in linhas:
            conn.execute(
                text("""
                    INSERT INTO tecnicos (id_tecnico_responsavel, nome, primeira_visita, ultima_visita)
                    VALUES (:id, :nome, :primeira, :ultima)
                    ON CONFLICT (id_tecnico_responsavel) DO UPDATE
                    SET nome = EXCLUDED.nome,
                        primeira_visita = LEAST(tecnicos.primeira_visita, EXCLUDED.primeira_visita),
                        ultima_visita = GREATEST(tecnicos.ultima_visita, EXCLUDED.ultima_visita),
                        atualizado_em = NOW();
                """),
                {
                    "id": int(l["id_tecnico_responsavel"]),
                    "nome": (l["tecnico_responsavel"] or "").strip(),
                    "primeira": l["primeira_visita"],
                    "ultima": l["ultima_visita"],
                },
            )
            processados += 1
    return processados


def sincronizar_tecnico_atividades():
    """
    Atualiza a tabela tecnico_atividades — cada combinação (técnico +
    projeto + atividade) vira uma linha, com a contagem de propriedades
    atendidas até hoje (todo o histórico, mesmo filtro de
    sincronizar_tecnicos_da_visita). Um técnico pode ter várias linhas
    (uma por atividade). Só sincroniza técnico que já exista na tabela
    mestra 'tecnicos' (rode sincronizar_tecnicos_da_visita antes, ou junto).
    """
    engine = get_engine()
    query = """
        SELECT
            id_tecnico_responsavel,
            tecnico_responsavel,
            projeto,
            atividade,
            COUNT(DISTINCT id_propriedade) AS propriedades_atendidas,
            MIN(dt_visita_v::date) AS primeira_visita,
            MAX(dt_visita_v::date) AS ultima_visita
        FROM public.acompanhamento_mensal_visitas
        WHERE dt_visita_v::date <= CURRENT_DATE
          AND flg_coleta_dados = 'Não'
          AND id_tecnico_responsavel IS NOT NULL
        GROUP BY id_tecnico_responsavel, tecnico_responsavel, projeto, atividade;
    """
    with engine.connect() as conn:
        linhas = conn.execute(text(query)).mappings().all()

    processados = 0
    with engine.begin() as conn:
        for l in linhas:
            existe = conn.execute(
                text("SELECT 1 FROM tecnicos WHERE id_tecnico_responsavel = :id"),
                {"id": int(l["id_tecnico_responsavel"])},
            ).fetchone()
            if not existe:
                continue

            conn.execute(
                text("""
                    INSERT INTO tecnico_atividades
                        (id_tecnico_responsavel, projeto, atividade, propriedades_atendidas, primeira_visita, ultima_visita)
                    VALUES
                        (:id, :projeto, :atividade, :propriedades, :primeira, :ultima)
                    ON CONFLICT (id_tecnico_responsavel, projeto, atividade) DO UPDATE
                    SET propriedades_atendidas = EXCLUDED.propriedades_atendidas,
                        primeira_visita = EXCLUDED.primeira_visita,
                        ultima_visita = EXCLUDED.ultima_visita,
                        atualizado_em = NOW();
                """),
                {
                    "id": int(l["id_tecnico_responsavel"]),
                    "projeto": l["projeto"],
                    "atividade": l["atividade"],
                    "propriedades": l["propriedades_atendidas"],
                    "primeira": l["primeira_visita"],
                    "ultima": l["ultima_visita"],
                },
            )
            processados += 1
    return processados


def listar_atividades_do_tecnico(id_tecnico_responsavel: int):
    """Todas as combinações projeto+atividade de um técnico (pode ter mais de uma)."""
    engine = get_engine()
    with engine.connect() as conn:
        linhas = conn.execute(
            text("""
                SELECT * FROM tecnico_atividades
                WHERE id_tecnico_responsavel = :id
                ORDER BY projeto, atividade;
            """),
            {"id": id_tecnico_responsavel},
        ).mappings().all()
    return [dict(l) for l in linhas]