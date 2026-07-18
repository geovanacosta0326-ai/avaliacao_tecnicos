import bcrypt
from sqlalchemy import text
from app.database import get_engine


def hash_senha(senha_pura: str) -> str:
    hash_bytes = bcrypt.hashpw(senha_pura.encode("utf-8"), bcrypt.gensalt())
    return hash_bytes.decode("utf-8")


def verificar_senha(senha_pura: str, senha_hash: str) -> bool:
    return bcrypt.checkpw(senha_pura.encode("utf-8"), senha_hash.encode("utf-8"))


def buscar_usuario(login: str):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, supervisor, login, senha_hash, tipo, precisa_trocar_senha
                FROM usuarios_supervisores
                WHERE login = :login;
            """),
            {"login": login},
        ).fetchone()
    return row


def autenticar(login: str, senha: str):
    """Retorna a linha do usuário se login/senha estiverem corretos, senão None."""
    usuario = buscar_usuario(login)
    if usuario is None:
        return None
    if not verificar_senha(senha, usuario.senha_hash):
        return None
    return usuario


def atualizar_senha(login: str, nova_senha: str):
    engine = get_engine()
    novo_hash = hash_senha(nova_senha)
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE usuarios_supervisores
                SET senha_hash = :novo_hash,
                    precisa_trocar_senha = FALSE,
                    atualizado_em = NOW()
                WHERE login = :login;
            """),
            {"novo_hash": novo_hash, "login": login},
        )


def criar_usuario(supervisor: str, login: str, senha_provisoria: str, tipo: str = "supervisor"):
    """
    Usado no cadastro inicial de cada usuário.
    tipo = 'supervisor' -> só vê/avalia os próprios técnicos.
    tipo = 'coordenador' -> vê o resumo de todos os supervisores (visão geral, sem avaliar).
    """
    engine = get_engine()
    senha_hash = hash_senha(senha_provisoria)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO usuarios_supervisores (supervisor, login, senha_hash, tipo, precisa_trocar_senha)
                VALUES (:supervisor, :login, :senha_hash, :tipo, TRUE)
                ON CONFLICT (login) DO NOTHING;
            """),
            {"supervisor": supervisor, "login": login, "senha_hash": senha_hash, "tipo": tipo},
        )


def definir_tipo_usuario(login: str, tipo: str):
    """
    Promove/rebaixa um login JÁ EXISTENTE para 'coordenador' ou 'supervisor',
    sem mexer na senha atual dele.
    """
    engine = get_engine()
    with engine.begin() as conn:
        resultado = conn.execute(
            text("""
                UPDATE usuarios_supervisores
                SET tipo = :tipo, atualizado_em = NOW()
                WHERE login = :login;
            """),
            {"tipo": tipo, "login": login},
        )
    return resultado.rowcount > 0
