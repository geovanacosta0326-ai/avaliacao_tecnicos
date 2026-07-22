"""
Mede quanto tempo a consulta que alimenta a tela "Supervisores"
(listar_vinculos_de_todos_os_supervisores) leva pra rodar, sozinha,
sem passar pelo navegador/servidor web -- só banco de dados.

Rode assim, na raiz do projeto (onde tem o .env):
    python diagnostico_tela_supervisores.py

Rode esse MESMO script tanto na sua máquina local quanto (se possível)
de algum jeito a partir do ambiente do Render, pra comparar os tempos.
"""
import time
from app.repositorio_vinculo_tecnico import listar_vinculos_de_todos_os_supervisores

print("Rodando listar_vinculos_de_todos_os_supervisores()...")
inicio = time.time()
resultado = listar_vinculos_de_todos_os_supervisores()
duracao = time.time() - inicio

total_supervisores = len(resultado)
total_vinculos = sum(len(v) for v in resultado.values())

print(f"\nDuração: {duracao:.2f} segundos")
print(f"Supervisores encontrados: {total_supervisores}")
print(f"Total de vínculos (linhas): {total_vinculos}")
