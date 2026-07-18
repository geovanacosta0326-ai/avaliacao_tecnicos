"""
Promove um login JÁ EXISTENTE (ex: criado sem querer como supervisor comum)
para o tipo 'coordenador', sem mexer na senha que já foi definida.

USO:
    python promover_coordenador.py login_existente
"""
import sys
from app.auth import definir_tipo_usuario


def main():
    if len(sys.argv) != 2:
        print("Uso: python promover_coordenador.py login_existente")
        return
    login = sys.argv[1]
    ok = definir_tipo_usuario(login, "coordenador")
    if ok:
        print(f"✔ Login '{login}' agora é COORDENADOR GERAL.")
    else:
        print(f"✘ Não encontrei nenhum usuário com login '{login}'.")


if __name__ == "__main__":
    main()
