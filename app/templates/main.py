import os
import json
from datetime import date
from fastapi import FastAPI, Request, Form, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

from app import auth, repositorio, avaliacoes

load_dotenv()

app = FastAPI(title="Avaliação de Técnicos")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "troque-esta-chave"))
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def supervisor_logado(request: Request) -> str | None:
    return request.session.get("supervisor")


def exigir_login(request: Request):
    supervisor = supervisor_logado(request)
    if not supervisor:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return supervisor


# ══════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════
@app.get("/login")
def tela_login(request: Request):
    if supervisor_logado(request):
        return RedirectResponse("/")
    return templates.TemplateResponse("login.html", {"request": request, "erro": None})


@app.post("/login")
def fazer_login(request: Request, login: str = Form(...), senha: str = Form(...)):
    usuario = auth.autenticar(login, senha)
    if usuario is None:
        return templates.TemplateResponse(
            "login.html", {"request": request, "erro": "Login ou senha inválidos."}
        )

    request.session["supervisor"] = usuario.supervisor
    request.session["login"] = usuario.login
    request.session["tipo"] = usuario.tipo

    if usuario.precisa_trocar_senha:
        return RedirectResponse("/trocar-senha", status_code=303)
    if usuario.tipo == "coordenador":
        return RedirectResponse("/coordenador", status_code=303)
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ══════════════════════════════════════════════════════════
# TROCAR SENHA (obrigatório no primeiro acesso)
# ══════════════════════════════════════════════════════════
@app.get("/trocar-senha")
def tela_trocar_senha(request: Request):
    if not supervisor_logado(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("trocar_senha.html", {"request": request, "erro": None})


@app.post("/trocar-senha")
def trocar_senha(request: Request, nova_senha: str = Form(...), confirmar_senha: str = Form(...)):
    login = request.session.get("login")
    if not login:
        return RedirectResponse("/login", status_code=303)

    if nova_senha != confirmar_senha:
        return templates.TemplateResponse(
            "trocar_senha.html", {"request": request, "erro": "As senhas não conferem."}
        )
    if len(nova_senha) < 6:
        return templates.TemplateResponse(
            "trocar_senha.html", {"request": request, "erro": "A senha deve ter pelo menos 6 caracteres."}
        )

    auth.atualizar_senha(login, nova_senha)
    if request.session.get("tipo") == "coordenador":
        return RedirectResponse("/coordenador", status_code=303)
    return RedirectResponse("/", status_code=303)


def lista_meses_para_template():
    return [
        {"valor": m.strftime("%Y-%m"), "label": m.strftime("%m/%Y")}
        for m in repositorio.meses_disponiveis_para_avaliacao()
    ]


# ══════════════════════════════════════════════════════════
# PAINEL DO SUPERVISOR
#   Passo 1: escolher o mês/ano de referência (tela "escolher_mes.html")
#   Passo 2: lista de técnicos daquele mês, com status avaliado/pendente
# ══════════════════════════════════════════════════════════
@app.get("/")
def painel(request: Request, mes: str | None = Query(default=None)):
    supervisor = supervisor_logado(request)
    if not supervisor:
        return RedirectResponse("/login", status_code=303)
    if request.session.get("tipo") == "coordenador":
        return RedirectResponse("/coordenador", status_code=303)

    meses_disponiveis = lista_meses_para_template()

    # Passo 1 — ainda não escolheu o mês: mostra a tela de seleção.
    if not mes:
        return templates.TemplateResponse(
            "escolher_mes.html",
            {
                "request": request,
                "supervisor": supervisor,
                "meses_disponiveis": meses_disponiveis,
            },
        )

    # Passo 2 — mês escolhido: mostra os técnicos com o status daquele mês.
    mes_ref = resolver_mes_escolhido(mes)
    tecnicos = repositorio.tecnicos_com_status_para_mes(supervisor, mes_ref)
    return templates.TemplateResponse(
        "painel.html",
        {
            "request": request,
            "supervisor": supervisor,
            "tecnicos": tecnicos,
            "mes_referencia": mes_ref.strftime("%m/%Y"),
            "mes_valor": mes_ref.strftime("%Y-%m"),
        },
    )


# ══════════════════════════════════════════════════════════
# HISTÓRICO DO SUPERVISOR — suas avaliações já feitas, por mês
# ══════════════════════════════════════════════════════════
@app.get("/minhas-avaliacoes")
def minhas_avaliacoes(request: Request):
    supervisor = supervisor_logado(request)
    if not supervisor:
        return RedirectResponse("/login", status_code=303)

    eh_coordenador = request.session.get("tipo") == "coordenador"
    if eh_coordenador:
        grupos = repositorio.avaliacoes_geral()
    else:
        grupos = repositorio.avaliacoes_do_supervisor(supervisor)

    return templates.TemplateResponse(
        "historico.html",
        {
            "request": request,
            "supervisor": supervisor,
            "grupos": grupos,
            "eh_coordenador": eh_coordenador,
        },
    )


@app.get("/minhas-avaliacoes/{avaliacao_id}")
def detalhe_avaliacao(request: Request, avaliacao_id: int):
    supervisor = supervisor_logado(request)
    if not supervisor:
        return RedirectResponse("/login", status_code=303)

    eh_coordenador = request.session.get("tipo") == "coordenador"
    if eh_coordenador:
        avaliacao = repositorio.buscar_avaliacao_por_id_admin(avaliacao_id)
    else:
        avaliacao = repositorio.buscar_avaliacao_por_id(avaliacao_id, supervisor)
    if avaliacao is None:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

    blocos = avaliacoes.montar_blocos_para_exibicao(avaliacao)
    return templates.TemplateResponse(
        "avaliacao_detalhe.html",
        {
            "request": request,
            "avaliacao": avaliacao,
            "blocos": blocos,
            "mes_referencia": avaliacao["mes_referencia"].strftime("%m/%Y"),
        },
    )


# ══════════════════════════════════════════════════════════
# VISÃO DO COORDENADOR GERAL — todos os supervisores
# ══════════════════════════════════════════════════════════
@app.get("/coordenador")
def painel_coordenador(request: Request):
    if not supervisor_logado(request):
        return RedirectResponse("/login", status_code=303)
    if request.session.get("tipo") != "coordenador":
        raise HTTPException(status_code=403, detail="Acesso restrito ao coordenador geral.")

    resumo, mes_ref = repositorio.resumo_geral_supervisores()
    total_tecnicos = sum(s["total"] for s in resumo)
    total_avaliados = sum(s["avaliados"] for s in resumo)

    return templates.TemplateResponse(
        "coordenador.html",
        {
            "request": request,
            "resumo": resumo,
            "mes_referencia": mes_ref.strftime("%m/%Y"),
            "total_tecnicos": total_tecnicos,
            "total_avaliados": total_avaliados,
        },
    )


# ══════════════════════════════════════════════════════════
# FORMULÁRIO DE AVALIAÇÃO
# ══════════════════════════════════════════════════════════
def resolver_mes_escolhido(mes: str | None) -> date:
    """
    Converte o parâmetro `mes` (ex: "2026-05" ou "2026-05-01") vindo da URL/form
    em uma data válida, MAS só aceita meses da lista de meses permitidos
    (mês corrente ou anterior, dentro da janela liberada) — nunca um valor
    arbitrário digitado na URL. Se não vier nada, ou vier algo inválido,
    cai no padrão (mês anterior ao atual).
    """
    permitidos = repositorio.meses_disponiveis_para_avaliacao()
    if not mes:
        return permitidos[0]
    try:
        partes = mes.split("-")
        candidato = date(int(partes[0]), int(partes[1]), 1)
    except (ValueError, IndexError):
        return permitidos[0]
    return candidato if candidato in permitidos else permitidos[0]


@app.get("/avaliar/{tecnico}")
def tela_avaliar(request: Request, tecnico: str, mes: str | None = Query(default=None)):
    supervisor = supervisor_logado(request)
    if not supervisor:
        return RedirectResponse("/login", status_code=303)

    tecnicos_permitidos = repositorio.listar_tecnicos_do_supervisor(supervisor)
    tecnico_real = repositorio.encontrar_tecnico(tecnico, tecnicos_permitidos)
    if tecnico_real is None:
        raise HTTPException(status_code=403, detail="Você não pode avaliar este técnico.")
    tecnico = tecnico_real  # a partir daqui, sempre o nome exato como está no banco

    mes_ref = resolver_mes_escolhido(mes)
    meses_disponiveis = lista_meses_para_template()

    if avaliacoes.ja_avaliado(supervisor, tecnico, mes_ref):
        return templates.TemplateResponse(
            "ja_avaliado.html",
            {
                "request": request,
                "tecnico": tecnico,
                "mes_referencia": mes_ref.strftime("%m/%Y"),
                "mes_referencia_valor": mes_ref.strftime("%Y-%m"),
                "meses_disponiveis": meses_disponiveis,
            },
        )

    return templates.TemplateResponse(
        "formulario.html",
        {
            "request": request,
            "supervisor": supervisor,
            "tecnico": tecnico,
            "mes_referencia": mes_ref.strftime("%m/%Y"),
            "mes_referencia_valor": mes_ref.strftime("%Y-%m"),
            "meses_disponiveis": meses_disponiveis,
        },
    )


@app.post("/avaliar/{tecnico}")
async def salvar_avaliacao(request: Request, tecnico: str):
    supervisor = supervisor_logado(request)
    if not supervisor:
        return RedirectResponse("/login", status_code=303)

    tecnicos_permitidos = repositorio.listar_tecnicos_do_supervisor(supervisor)
    tecnico_real = repositorio.encontrar_tecnico(tecnico, tecnicos_permitidos)
    if tecnico_real is None:
        raise HTTPException(status_code=403, detail="Você não pode avaliar este técnico.")
    tecnico = tecnico_real  # a partir daqui, sempre o nome exato como está no banco

    form = await request.form()
    mes_ref = resolver_mes_escolhido(form.get("mes_referencia"))

    if avaliacoes.ja_avaliado(supervisor, tecnico, mes_ref):
        return RedirectResponse("/", status_code=303)

    respostas = {campo: form.get(campo) for campo in avaliacoes.TODOS_OS_CAMPOS}

    media = avaliacoes.salvar_avaliacao(supervisor, tecnico, mes_ref, respostas)

    return templates.TemplateResponse(
        "sucesso.html",
        {
            "request": request, "tecnico": tecnico, "media": media,
            "mes_referencia_valor": mes_ref.strftime("%Y-%m"),
        },
    )


# ══════════════════════════════════════════════════════════
# COMPARAR AVALIAÇÕES DE UM TÉCNICO ENTRE MESES
# ══════════════════════════════════════════════════════════
@app.get("/comparar/{tecnico}")
def comparar_avaliacoes(request: Request, tecnico: str, sup: str | None = Query(default=None)):
    supervisor_logado_nome = supervisor_logado(request)
    if not supervisor_logado_nome:
        return RedirectResponse("/login", status_code=303)

    eh_coordenador = request.session.get("tipo") == "coordenador"
    if eh_coordenador:
        # Coordenador geral pode ver qualquer técnico, de qualquer supervisor,
        # desde que informe de qual supervisor é (vem do link do histórico geral).
        if not sup:
            raise HTTPException(status_code=400, detail="Supervisor não informado.")
        supervisor = sup
        tecnico_real = tecnico
    else:
        supervisor = supervisor_logado_nome
        tecnicos_permitidos = repositorio.listar_tecnicos_do_supervisor(supervisor)
        tecnico_real = repositorio.encontrar_tecnico(tecnico, tecnicos_permitidos)
        if tecnico_real is None:
            raise HTTPException(status_code=403, detail="Você não pode ver este técnico.")

    lista_avaliacoes = repositorio.avaliacoes_do_tecnico(supervisor, tecnico_real)
    if not lista_avaliacoes:
        return templates.TemplateResponse(
            "comparacao.html",
            {
                "request": request, "tecnico": tecnico_real,
                "meses": [], "itens": [], "media_valores": [],
                "labels_grafico": "[]", "valores_grafico": "[]", "crescimento": None,
            },
        )

    meses, itens, media_valores = avaliacoes.montar_tabela_resumida(lista_avaliacoes)

    # Dados para o gráfico de evolução (linha do tempo da média final por mês).
    valores_numericos = [float(v) if v not in (None, "") else None for v in media_valores]
    labels_grafico = json.dumps(meses)
    valores_grafico = json.dumps(valores_numericos)

    crescimento = None
    validos = [v for v in valores_numericos if v is not None]
    if len(validos) >= 2:
        crescimento = round(validos[-1] - validos[0], 2)

    return templates.TemplateResponse(
        "comparacao.html",
        {
            "request": request,
            "tecnico": tecnico_real,
            "meses": meses,
            "itens": itens,
            "media_valores": media_valores,
            "labels_grafico": labels_grafico,
            "valores_grafico": valores_grafico,
            "crescimento": crescimento,
        },
    )
