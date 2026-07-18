"""
Script de apoio para cadastrar o login de um supervisor.

USO:
    1) Listar os supervisores que existem no banco (nome exato usado lá):
       python cadastrar_supervisor.py listar

    2) Cadastrar o login de um supervisor (copie o nome EXATO da lista acima):
       python cadastrar_supervisor.py criar "Nome Exato Do Supervisor" login_desejado senha_provisoria
"""
import sys
from app.repositorio import listar_supervisores
from app.auth import criar_usuario


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    comando = sys.argv[1]

    if comando == "listar":
        supervisores = listar_supervisores()
        if not supervisores:
            print("Nenhum supervisor encontrado na base (confira a conexão com o banco).")
            return
        print(f"\n{len(supervisores)} supervisor(es) encontrado(s) na base:\n")
        for s in supervisores:
            print(f"  - {s}")
        print()

    elif comando == "criar":
        if len(sys.argv) != 5:
            print('Uso: python cadastrar_supervisor.py criar "Nome Exato Do Supervisor" login senha_provisoria')
            return
        _, _, supervisor, login, senha = sys.argv
        criar_usuario(supervisor=supervisor, login=login, senha_provisoria=senha)
        print(f"✔ Usuário '{login}' criado para o supervisor '{supervisor}'.")
        print("  Ele vai precisar trocar a senha no primeiro acesso.")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
