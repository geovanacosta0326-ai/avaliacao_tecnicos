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
    """Lista os técnicos vinculados atualmente a um supervisor específico."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT tecnico
                FROM ({QUERY_SUPERVISOR_POR_TECNICO}) base
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


def tecnicos_com_status_para_mes(supervisor: str, mes_ref: date):
    """
    Retorna a lista de técnicos do supervisor + se já foram avaliados
    NO MÊS ESCOLHIDO (mes_ref) — usado depois que o supervisor seleciona
    o mês/ano na tela inicial e entra na tela dos técnicos.
    """
    tecnicos = listar_tecnicos_do_supervisor(supervisor)

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tecnico
                FROM avaliacoes_tecnicos
                WHERE supervisor = :supervisor AND mes_referencia = :mes_ref;
            """),
            {"supervisor": supervisor, "mes_ref": mes_ref},
        ).fetchall()
    ja_avaliados = {r.tecnico for r in rows}

    return [
        {"tecnico": t, "avaliado": t in ja_avaliados}
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
    cada avaliação dentro do grupo tem: id, tecnico, media_final, data_avaliacao.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, tecnico, mes_referencia, media_final, data_avaliacao
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
            "media_final": r.media_final,
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
    cada avaliação dentro do grupo tem: id, supervisor, tecnico, media_final, data_avaliacao.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, supervisor, tecnico, mes_referencia, media_final, data_avaliacao
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
            "media_final": r.media_final,
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


def resumo_geral_supervisores():
    """
    Visão do coordenador: para cada supervisor, quantos técnicos ele tem e
    quantos já foram avaliados no mês de referência atual.
    """
    engine = get_engine()
    mes_ref = mes_referencia_atual()

    with engine.connect() as conn:
        tecnicos_por_supervisor = conn.execute(
            text(f"SELECT supervisor, tecnico FROM ({QUERY_SUPERVISOR_POR_TECNICO}) base")
        ).fetchall()

        avaliados = conn.execute(
            text("""
                SELECT supervisor, tecnico
                FROM avaliacoes_tecnicos
                WHERE mes_referencia = :mes_ref;
            """),
            {"mes_ref": mes_ref},
        ).fetchall()

    avaliados_set = {(r.supervisor, r.tecnico) for r in avaliados}

    resumo = {}
    for r in tecnicos_por_supervisor:
        item = resumo.setdefault(r.supervisor, {"supervisor": r.supervisor, "total": 0, "avaliados": 0})
        item["total"] += 1
        if (r.supervisor, r.tecnico) in avaliados_set:
            item["avaliados"] += 1

    lista = sorted(resumo.values(), key=lambda x: x["supervisor"])
    for item in lista:
        item["pendentes"] = item["total"] - item["avaliados"]
    return lista, mes_ref
