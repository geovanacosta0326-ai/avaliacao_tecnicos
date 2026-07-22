"""
Converte as notas finais JA LANCADAS (avaliacoes_tecnicos.nota_final) da
escala antiga (soma das 10 perguntas, 50-100) para a escala nova (media
das 10 perguntas, 5.0-10.0) -- ou seja, divide por 10 quem ainda estiver
na escala antiga.

SEGURO RODAR MAIS DE UMA VEZ: so converte linhas com nota_final > 10 (ou
seja, ainda na escala antiga). Depois de convertida, uma nota fica <= 10
e nao é mexida de novo se voce rodar o script outra vez.

Faz backup em CSV antes de alterar qualquer coisa.

Rode assim, na raiz do projeto (onde tem o .env):
    python converter_nota_final_para_media.py

Ele pede confirmacao antes de gravar de verdade.
"""
import csv
import os
from datetime import datetime
from sqlalchemy import text
from app.database import get_engine

engine = get_engine()

with engine.connect() as conn:
    linhas = conn.execute(
        text("SELECT id, supervisor, tecnico, mes_referencia, nota_final FROM avaliacoes_tecnicos WHERE nota_final > 10 ORDER BY id;")
    ).mappings().all()

if not linhas:
    print("Nenhuma nota na escala antiga (>10) encontrada -- nada para converter.")
    raise SystemExit(0)

print(f"{len(linhas)} avaliação(ões) na escala antiga (soma, 50-100) serão convertidas para média (5.0-10.0).\n")
print("Exemplos:")
for l in linhas[:5]:
    nova = round(l["nota_final"] / 10.0, 2)
    print(f"  id={l['id']}  {l['tecnico']}  {l['mes_referencia']}  {l['nota_final']} -> {nova}")

pasta_backup = f"backup_nota_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
os.makedirs(pasta_backup, exist_ok=True)
caminho = os.path.join(pasta_backup, "avaliacoes_tecnicos_antes_da_conversao.csv")
with open(caminho, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=linhas[0].keys())
    writer.writeheader()
    for l in linhas:
        writer.writerow(dict(l))
print(f"\nBackup salvo em: {caminho}")

confirmacao = input(f"\nConfirma a conversão de {len(linhas)} nota(s)? Digite SIM para continuar: ")
if confirmacao.strip().upper() != "SIM":
    print("Cancelado -- nada foi alterado.")
    raise SystemExit(0)

with engine.begin() as conn:
    conn.execute(
        text("""
            UPDATE avaliacoes_tecnicos
            SET nota_final = ROUND(nota_final / 10.0, 2)
            WHERE nota_final > 10;
        """)
    )

print(f"\n✔ {len(linhas)} nota(s) convertida(s) com sucesso para a escala 5.0-10.0.")
