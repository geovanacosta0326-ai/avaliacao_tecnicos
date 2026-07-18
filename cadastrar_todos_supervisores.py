"""
Cadastra automaticamente TODOS os supervisores que já existem no banco de
dados (mesma fonte usada no rank), gerando um login simples para cada um
e uma senha provisória. Cada supervisor troca a própria senha no primeiro
acesso ao sistema.

USO:
    python cadastrar_todos_supervisores.py

Depois de rodar, ele mostra na tela o login e a senha provisória de cada
supervisor — anote e repasse pra cada um deles.
"""
import re
import secrets
import string
from app.repositorio import listar_supervisores
from app.auth import criar_usuario, buscar_usuario


def gerar_login(nome_supervisor: str) -> str:
    """
    Gera um login simples a partir do nome, ex:
    'João da Silva Souza' -> 'joao.silva'  (primeiro + segundo nome)
    """
    nome_limpo = nome_supervisor.strip().lower()
    nome_limpo = (
        nome_limpo.replace("á", "a").replace("à", "a").replace("â", "a").replace("ã", "a")
        .replace("é", "e").replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o").replace("ô", "o").replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )
    partes = re.sub(r"[^a-z\s]", "", nome_limpo).split()
    conectivos = {"da", "de", "do", "das", "dos", "e"}
    partes_validas = [p for p in partes if p not in conectivos]

    if not partes_validas:
        return "supervisor"
    if len(partes_validas) == 1:
        return partes_validas[0]
    return f"{partes_validas[0]}.{partes_validas[-1]}"


def gerar_senha_provisoria(tamanho: int = 8) -> str:
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(tamanho))


def main():
    supervisores = listar_supervisores()
    if not supervisores:
        print("Nenhum supervisor encontrado no banco. Confira a conexão (.env).")
        return

    print(f"\n{len(supervisores)} supervisor(es) encontrado(s) na base.\n")
    print(f"{'SUPERVISOR':<35} {'LOGIN':<20} {'SENHA PROVISÓRIA'}")
    print("-" * 75)

    logins_usados = {}
    resultados = []

    for nome in supervisores:
        login_base = gerar_login(nome)
        login = login_base
        contador = 2
        # evita logins duplicados (ex: dois "João Silva" diferentes)
        while login in logins_usados or buscar_usuario(login) is not None:
            login = f"{login_base}{contador}"
            contador += 1
        logins_usados[login] = nome

        senha = gerar_senha_provisoria()
        criar_usuario(supervisor=nome, login=login, senha_provisoria=senha)
        resultados.append((nome, login, senha))
        print(f"{nome:<35} {login:<20} {senha}")

    print("\n✔ Cadastro concluído. Guarde essa lista com segurança e repasse")
    print("  o login e a senha provisória de cada supervisor individualmente.")
    print("  Cada um vai trocar a própria senha no primeiro acesso.\n")


if __name__ == "__main__":
    main()
