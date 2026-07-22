from sqlalchemy import text
from app.database import get_engine

# As 10 perguntas do questionário ATeG — todas de NOTA (5 a 10).
# Substitui o questionário antigo de 25 perguntas (ver avaliacoes_tecnicos_legado).
CAMPOS_NOTA = [
    "p1_dominio_metodologia",
    "p2_qualidade_orientacoes",
    "p3_planejamento",
    "p4_registros_sisateg",
    "p5_relatorios_mensais",
    "p6_cumprimento_prazos",
    "p7_acompanhamento_evolucao",
    "p8_comunicacao_produtores",
    "p9_comprometimento_normas",
    "p10_desempenho_geral",
]

TODOS_OS_CAMPOS = CAMPOS_NOTA  # não há mais campos de texto/Sim-Não no novo formulário

# Palavra-chave curta de cada pergunta — usada na tabela resumida da tela de evolução.
ROTULO_CURTO = {
    "p1_dominio_metodologia": "Domínio metodologia ATeG",
    "p2_qualidade_orientacoes": "Qualidade das orientações",
    "p3_planejamento": "Planejamento (metas/SWOT/PA)",
    "p4_registros_sisateg": "Registros no SISATEG",
    "p5_relatorios_mensais": "Relatórios mensais",
    "p6_cumprimento_prazos": "Cumprimento de prazos",
    "p7_acompanhamento_evolucao": "Acompanhamento da evolução",
    "p8_comunicacao_produtores": "Comunicação com produtores",
    "p9_comprometimento_normas": "Comprometimento com normas",
    "p10_desempenho_geral": "Desempenho geral",
}

# Rótulo (pergunta por extenso), um único bloco — o formulário ATeG não tem
# mais divisão por blocos temáticos, é uma lista direta de 10 perguntas.
PERGUNTAS = [
    ("Questionário ATeG", [
        ("p1_dominio_metodologia", "Como você avalia o domínio do técnico sobre a metodologia ATeG durante a execução das visitas?"),
        ("p2_qualidade_orientacoes", "Como você avalia a qualidade das orientações técnicas/gerenciais repassadas aos produtores?"),
        ("p3_planejamento", "Como você avalia a elaboração e execução do planejamento (metas, matriz SWOT e plano de ação)?"),
        ("p4_registros_sisateg", "Como você avalia a qualidade dos registros realizados no SISATEG (check-in, check-out, fotos, localização e preenchimento dos dados produtivos, receitas e despesas e inventário de recursos)?"),
        ("p5_relatorios_mensais", "Como você avalia a qualidade técnica e a consistência dos relatórios mensais elaborados pelo técnico?"),
        ("p6_cumprimento_prazos", "Como você avalia o cumprimento dos prazos para envio de relatórios e demais atividades?"),
        ("p7_acompanhamento_evolucao", "Como você avalia a capacidade do técnico em acompanhar a evolução das propriedades e verificar o cumprimento das recomendações anteriores?"),
        ("p8_comunicacao_produtores", "Como você avalia a comunicação e o relacionamento do técnico com os produtores rurais?"),
        ("p9_comprometimento_normas", "Como você avalia o comprometimento do técnico com as orientações da supervisão e as normas do programa ATeG?"),
        ("p10_desempenho_geral", "Considerando o desempenho geral, como você avalia a atuação do técnico no programa ATeG?"),
    ]),
]


def classificar(nota_final) -> str:
    """Classificação conforme a faixa da nota final (média das 10 perguntas, 5.0-10.0)."""
    if nota_final >= 9:
        return "Desempenho Excelente"
    if nota_final >= 8:
        return "Muito Bom"
    if nota_final >= 7:
        return "Bom"
    if nota_final >= 6:
        return "Regular"
    return "Necessita Melhoria"


def montar_blocos_para_exibicao(avaliacao: dict):
    """
    Transforma o registro salvo no banco (dict com colunas cruas) na estrutura
    de blocos/perguntas/respostas pronta para o template de detalhe.
    """
    blocos = []
    for titulo, campos in PERGUNTAS:
        itens = [
            {"pergunta": pergunta, "resposta": avaliacao.get(campo)}
            for campo, pergunta in campos
        ]
        blocos.append({"titulo": titulo, "itens": itens})
    return blocos


def montar_tabela_resumida(lista_avaliacoes: list[dict]):
    """
    Uma linha por pergunta (usando a palavra-chave curta), uma coluna por mês.
    Usada na tela de evolução.
    """
    meses = [a["mes_referencia"].strftime("%m/%Y") for a in lista_avaliacoes]

    itens = []
    for campo in CAMPOS_NOTA:
        rotulo = ROTULO_CURTO.get(campo, campo)
        valores = []
        anterior = None
        for a in lista_avaliacoes:
            v = a.get(campo)
            delta = None
            if v not in (None, "") and anterior not in (None, ""):
                try:
                    delta = float(v) - float(anterior)
                except (TypeError, ValueError):
                    delta = None
            valores.append({"valor": v, "delta": delta})
            anterior = v
        itens.append({"rotulo": rotulo, "valores": valores})

    media_valores = [a.get("nota_final") for a in lista_avaliacoes]
    return meses, itens, media_valores


def montar_tabela_comparativa(lista_avaliacoes: list[dict]):
    """
    Monta a estrutura pronta para o template de comparação: uma linha por
    pergunta, uma coluna por mês avaliado, com delta em relação ao mês anterior.
    """
    meses = [a["mes_referencia"].strftime("%m/%Y") for a in lista_avaliacoes]

    linhas = []
    for titulo, campos in PERGUNTAS:
        itens = []
        for campo, pergunta in campos:
            valores = []
            anterior = None
            for a in lista_avaliacoes:
                v = a.get(campo)
                delta = None
                if v not in (None, "") and anterior not in (None, ""):
                    try:
                        delta = float(v) - float(anterior)
                    except (TypeError, ValueError):
                        delta = None
                valores.append({"valor": v, "delta": delta})
                anterior = v
            itens.append({"pergunta": pergunta, "eh_nota": True, "valores": valores})
        linhas.append({"titulo": titulo, "itens": itens})

    media_valores = [a.get("nota_final") for a in lista_avaliacoes]
    return meses, linhas, media_valores


def calcular_nota_final(respostas: dict) -> float:
    """Média das 10 notas (cada uma de 5 a 10): soma dividida por 10 —
    resultado fica sempre entre 5.0 e 10.0."""
    soma = sum(int(respostas[c]) for c in CAMPOS_NOTA)
    return round(soma / len(CAMPOS_NOTA), 2)


def ja_avaliado(supervisor: str, tecnico: str, mes_referencia) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT 1 FROM avaliacoes_tecnicos
                WHERE supervisor = :supervisor AND tecnico = :tecnico
                  AND mes_referencia = :mes_referencia;
            """),
            {"supervisor": supervisor, "tecnico": tecnico, "mes_referencia": mes_referencia},
        ).fetchone()
    return row is not None


def salvar_avaliacao(supervisor: str, tecnico: str, mes_referencia, respostas: dict):
    nota_final = calcular_nota_final(respostas)
    colunas = ", ".join(TODOS_OS_CAMPOS)
    placeholders = ", ".join(f":{c}" for c in TODOS_OS_CAMPOS)

    params = {c: int(respostas[c]) for c in TODOS_OS_CAMPOS}
    params.update({
        "supervisor": supervisor,
        "tecnico": tecnico,
        "mes_referencia": mes_referencia,
        "nota_final": nota_final,
    })

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(f"""
                INSERT INTO avaliacoes_tecnicos
                    (supervisor, tecnico, mes_referencia, {colunas}, nota_final)
                VALUES
                    (:supervisor, :tecnico, :mes_referencia, {placeholders}, :nota_final)
                ON CONFLICT (supervisor, tecnico, mes_referencia) DO NOTHING;
            """),
            params,
        )
    return nota_final
