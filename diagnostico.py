"""
Script de DIAGNOSTICO - roda no servidor de producao, dentro da pasta do projeto
(mesma pasta onde tem o .env e a pasta app/).

USO:
    python3 diagnostico.py

Nao precisa passar senha nem nada: ele usa o .env que ja esta configurado.
So imprime informacoes de estrutura (nomes de tabela/coluna/schema), nao
mostra dados sigilosos.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, URL, text

load_dotenv()

url = URL.create(
    "postgresql+psycopg",
    username=os.getenv("REMOTE_DB_USER", "postgres"),
    password=os.getenv("REMOTE_DB_PASS"),
    host=os.getenv("REMOTE_DB_HOST", "177.22.38.27"),
    port=int(os.getenv("REMOTE_DB_PORT", "6432")),
    database=os.getenv("REMOTE_DB_NAME", "painel_ateg"),
)

print(f"Conectando em: host={url.host} port={url.port} db={url.database} user={url.username}\n")

engine = create_engine(url, pool_pre_ping=True)

with engine.connect() as conn:
    quem_sou_eu = conn.execute(text("SELECT current_user, current_database();")).fetchone()
    print(f"Conectado como: {quem_sou_eu[0]}  |  Banco: {quem_sou_eu[1]}\n")

    print("== Procurando a tabela 'acompanhamento_mensal_visitas' em TODOS os schemas ==")
    achou = conn.execute(text("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_name = 'acompanhamento_mensal_visitas';
    """)).fetchall()

    if not achou:
        print("  -> NAO ENCONTREI a tabela em nenhum schema visivel para este usuario.")
        print("     Ou ela nao existe neste banco, ou este usuario nao tem permissao")
        print("     nem pra ENXERGAR que ela existe (falta GRANT).")
    else:
        for schema, nome in achou:
            print(f"  -> Encontrada em schema='{schema}', tabela='{nome}'")

        for schema, nome in achou:
            print(f"\n== Colunas de {schema}.{nome} ==")
            cols = conn.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :nome
                ORDER BY ordinal_position;
            """), {"schema": schema, "nome": nome}).fetchall()
            for c in cols:
                print(f"   - {c.column_name} ({c.data_type})")

            precisa = {"tecnico_responsavel", "supervisor_atual", "dt_visita"}
            existentes = {c.column_name for c in cols}
            faltando = precisa - existentes
            if faltando:
                print(f"\n   !! ATENCAO: faltam as colunas esperadas pelo sistema novo: {faltando}")
            else:
                print("\n   OK: todas as colunas que o sistema precisa estao presentes.")

            print(f"\n== Testando SELECT direto em {schema}.{nome} ==")
            try:
                teste = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{nome}";')).scalar()
                print(f"   -> SELECT funcionou. Total de linhas: {teste}")
            except Exception as e:
                print(f"   -> SELECT FALHOU: {e}")

    print("\n== Testando a mesma query EXATA que o sistema roda (schema 'public') ==")
    try:
        r = conn.execute(text("""
            SELECT DISTINCT ON (tecnico_responsavel)
                tecnico_responsavel AS tecnico,
                supervisor_atual     AS supervisor
            FROM public.acompanhamento_mensal_visitas
            WHERE tecnico_responsavel IS NOT NULL
              AND supervisor_atual IS NOT NULL
            ORDER BY tecnico_responsavel, dt_visita DESC
            LIMIT 3;
        """)).fetchall()
        print(f"   -> FUNCIONOU. Exemplo de linhas: {r}")
    except Exception as e:
        print(f"   -> FALHOU (esse e o erro real que o site esta dando): {e}")

print("\nDiagnostico concluido.")
