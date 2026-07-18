"""
Cadastra o login do COORDENADOR GERAL (acesso à visão de todos os supervisores).

USO:
    python cadastrar_coordenador.py "Seu Nome" login senha_provisoria
"""
import sys
from app.auth import criar_usuario


def main():
    if len(sys.argv) != 4:
        print('Uso: python cadastrar_coordenador.py "Seu Nome" login senha_provisoria')
        return
    _, nome, login, senha = sys.argv
    criar_usuario(supervisor=nome, login=login, senha_provisoria=senha, tipo="coordenador")
    print(f"✔ Coordenador '{login}' criado. Ele vai trocar a senha no primeiro acesso.")


if __name__ == "__main__":
    main()
