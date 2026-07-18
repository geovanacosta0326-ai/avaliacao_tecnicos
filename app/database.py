import os
from functools import lru_cache
from sqlalchemy import create_engine, URL
from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def get_engine():
    """
    Mesma conexão usada no painel Streamlit original.

    IMPORTANTE: @lru_cache faz essa função criar o engine (e o pool de
    conexões) UMA ÚNICA VEZ por execução do servidor, e reaproveitar nas
    chamadas seguintes. Sem isso, cada consulta ao banco (cada tela
    acessada) abria um pool de conexões novo que nunca era fechado —
    com o uso normal do sistema isso ia acumulando conexões abertas no
    banco remoto até estourar o limite, e a próxima tela que tentasse
    conectar ficava travada esperando uma conexão livre (é isso que
    causava a tela "carregando" sem nunca abrir).
    """
    url = URL.create(
        "postgresql+psycopg",
        username=os.getenv("REMOTE_DB_USER", "postgres"),
        password=os.getenv("REMOTE_DB_PASS"),
        host=os.getenv("REMOTE_DB_HOST", "177.22.38.27"),
        port=int(os.getenv("REMOTE_DB_PORT", "6432")),
        database=os.getenv("REMOTE_DB_NAME", "painel_ateg"),
    )
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
