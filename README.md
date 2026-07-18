# Sistema de Avaliação de Técnicos

Aplicação web (FastAPI) onde cada supervisor faz login e avalia mensalmente
apenas os técnicos vinculados a ele, com base no mesmo vínculo
supervisor↔técnico usado no painel de ranking (`supervisor_atual` mais
recente de cada técnico).

## Funcionalidades desta primeira etapa

- Login individual por supervisor, com troca de senha obrigatória no primeiro acesso
- Cada supervisor só enxerga e avalia os técnicos vinculados a ele
- Avaliação sempre referente ao **mês anterior** ao mês corrente
- Trava contra avaliação duplicada do mesmo técnico no mesmo mês
- Cálculo automático da nota final (média das perguntas de nota 5–10)

## Como rodar localmente

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # depois edite o .env com os dados reais do banco
```

Crie as tabelas novas no Postgres (sem mexer nas tabelas existentes):

```bash
psql "postgresql://usuario:senha@host:5432/banco" -f sql/schema.sql
```

Cadastre o primeiro supervisor (senha provisória), por exemplo num shell Python:

```python
from app.auth import criar_usuario
criar_usuario(supervisor="Nome Exato Como Está no Banco", login="fulano", senha_provisoria="1234senha")
```

Rode a aplicação:

```bash
uvicorn app.main:app --reload
```


Acesse http://localhost:8000/login

uvicorn app.main:app --port 8001 --reload
uvicorn app.main:app --port 8000 --reload

http://localhost:8000/login
## Estrutura

```
app/
  main.py          -> rotas (login, painel, formulário)
  database.py       -> conexão com o Postgres
  repositorio.py     -> consultas de supervisor/técnico (mesma regra do rank)
  auth.py            -> login, hash de senha, troca de senha
  avaliacoes.py       -> gravação das respostas + cálculo da média
  templates/          -> páginas HTML
  static/             -> CSS
sql/schema.sql         -> tabelas novas: usuarios_supervisores, avaliacoes_tecnicos
```

## Próximos passos (ainda não incluídos aqui)

- Tela de administração para cadastrar supervisores em lote
- Integração da nota da avaliação no ranking geral
- Histórico/gráfico de evolução do técnico mês a mês


https://avaliacao-tecnicos.onrender.com/login
