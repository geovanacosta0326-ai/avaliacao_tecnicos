"""
Importa vínculos de técnicos a partir da planilha geral (Excel), evitando
recadastro manual um por um.

USO:
    python importar_vinculos_planilha.py "PLANILHA_GERAL_-_16_07_2026.xlsx"

O QUE FAZ:
  1. Lê a planilha (colunas: Usuário, CPF, Supervisor, Nome Fantasia, CNPJ,
     CADEIA, INÍCIO, FIM, PROJETO).
  2. Para cada técnico, busca o nome EXATO como está gravado na base de
     visitas (acompanhamento_mensal_visitas) — usando a mesma comparação
     tolerante a acento/caixa/espaço que o resto do sistema já usa — para
     não gravar um nome que não bate com a base (o "ponto crítico de
     integração" do descritivo).
  3. Se achar o técnico: cria o vínculo em vinculo_tecnico (só se ele ainda
     não tiver um vínculo ATIVO — não sobrescreve nada que já exista).
  4. Se NÃO achar: pula e lista no final, para revisão manual.

SEGURANÇA: só faz INSERT quando não existe vínculo ativo para aquele
técnico (ON CONFLICT DO NOTHING) — nunca apaga ou sobrescreve um vínculo
que já esteja ativo (por exemplo, um que um supervisor já tenha cadastrado
manualmente pela tela).
"""
import sys
import unicodedata
import pandas as pd
from sqlalchemy import text

from app.database import get_engine


def normalizar(texto) -> str:
    """Mesma normalização usada em app/repositorio.py, para achar o nome oficial."""
    if texto is None or (isinstance(texto, float)):
        return ""
    texto = str(texto)
    texto = unicodedata.normalize("NFC", texto).strip()
    texto = " ".join(texto.split())
    return texto.casefold()


def limpar_supervisor(valor) -> str | None:
    """Remove ';' e espaços extras que aparecem no fim de vários nomes na planilha."""
    if valor is None or pd.isna(valor):
        return None
    return str(valor).strip().rstrip(";").strip()


def limpar_texto(valor) -> str | None:
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    return texto or None


def limpar_data(valor):
    if valor is None or pd.isna(valor):
        return None
    return valor.date() if hasattr(valor, "date") else valor


def main(caminho_planilha: str):
    print(f"Lendo planilha: {caminho_planilha}")
    df = pd.read_excel(caminho_planilha)
    df.columns = [c.strip() for c in df.columns]  # tira espaço de "CADEIA ", "INÍCIO " etc.

    engine = get_engine()

    # Nomes oficiais (como estão gravados na base de visitas) — usado para
    # achar o nome exato de cada técnico da planilha.
    with engine.connect() as conn:
        nomes_oficiais = [
            r[0] for r in conn.execute(
                text("""
                    SELECT DISTINCT tecnico_responsavel
                    FROM public.acompanhamento_mensal_visitas
                    WHERE tecnico_responsavel IS NOT NULL
                """)
            ).fetchall()
        ]
    mapa_normalizado = {normalizar(n): n for n in nomes_oficiais}

    importados = 0
    ja_existiam = 0
    nao_encontrados = []

    with engine.begin() as conn:
        for _, linha in df.iterrows():
            nome_planilha = limpar_texto(linha.get("Usuário"))
            if not nome_planilha:
                continue

            nome_oficial = mapa_normalizado.get(normalizar(nome_planilha))
            if nome_oficial is None:
                nao_encontrados.append(nome_planilha)
                continue

            supervisor = limpar_supervisor(linha.get("Supervisor"))
            if not supervisor:
                nao_encontrados.append(f"{nome_planilha} (sem supervisor preenchido na planilha)")
                continue

            params = {
                "tecnico": nome_oficial,
                "cpf": limpar_texto(linha.get("CPF")),
                "projeto": limpar_texto(linha.get("PROJETO")),
                "atividade": limpar_texto(linha.get("CADEIA")),
                "empresa": limpar_texto(linha.get("Nome Fantasia")),
                "cnpj_empresa": limpar_texto(linha.get("CNPJ")),
                "supervisor": supervisor,
                "data_inicio": limpar_data(linha.get("INÍCIO")),
                "data_fim_prevista": limpar_data(linha.get("FIM")),
                "criado_por": "importação planilha",
            }

            # Sem data de início na planilha: usa a data de hoje como início do vínculo.
            if params["data_inicio"] is None:
                from datetime import date
                params["data_inicio"] = date.today()

            resultado = conn.execute(
                text("""
                    INSERT INTO vinculo_tecnico
                        (tecnico, cpf, projeto, atividade, empresa, cnpj_empresa,
                         supervisor, data_inicio, data_fim_prevista, criado_por)
                    VALUES
                        (:tecnico, :cpf, :projeto, :atividade, :empresa, :cnpj_empresa,
                         :supervisor, :data_inicio, :data_fim_prevista, :criado_por)
                    ON CONFLICT (tecnico) WHERE data_desvinculacao IS NULL DO NOTHING
                """),
                params,
            )
            if resultado.rowcount:
                importados += 1
            else:
                ja_existiam += 1

    print(f"\nImportados: {importados}")
    print(f"Já tinham vínculo ativo (não mexido): {ja_existiam}")
    print(f"Não encontrados na base de visitas (não importados): {len(nao_encontrados)}")
    if nao_encontrados:
        print("\n--- Lista dos não encontrados (revisar manualmente) ---")
        for nome in nao_encontrados:
            print(f"  - {nome}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python importar_vinculos_planilha.py \"caminho\\da\\planilha.xlsx\"")
        sys.exit(1)
    main(sys.argv[1])
