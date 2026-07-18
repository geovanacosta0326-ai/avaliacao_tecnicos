-- ══════════════════════════════════════════════════════════
-- Prazo mensal para o supervisor avaliar os técnicos e
-- autorizações do coordenador para avaliações fora do prazo.
-- ══════════════════════════════════════════════════════════

-- Configuração única (id = 1) com o dia-limite do mês.
-- Ex.: dia_limite = 23 -> a avaliação referente a JUNHO fica aberta
-- até o dia 23 de JULHO; depois disso, só com autorização.
CREATE TABLE IF NOT EXISTS configuracao_prazo_avaliacao (
    id             SMALLINT PRIMARY KEY DEFAULT 1,
    dia_limite     SMALLINT NOT NULL DEFAULT 23,
    atualizado_em  TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_por TEXT,
    CHECK (id = 1)   -- garante que só existe 1 linha (configuração global)
);

INSERT INTO configuracao_prazo_avaliacao (id, dia_limite)
VALUES (1, 23)
ON CONFLICT (id) DO NOTHING;

-- Autorizações pontuais do coordenador para um supervisor continuar
-- avaliando um mês específico mesmo depois do prazo encerrado.
CREATE TABLE IF NOT EXISTS autorizacoes_avaliacao_atrasada (
    id             SERIAL PRIMARY KEY,
    supervisor     TEXT NOT NULL,
    mes_referencia DATE NOT NULL,
    autorizado_por TEXT NOT NULL,
    criado_em      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (supervisor, mes_referencia)
);

CREATE INDEX IF NOT EXISTS idx_autorizacoes_supervisor_mes
    ON autorizacoes_avaliacao_atrasada (supervisor, mes_referencia);

-- Prazo específico definido pelo coordenador para um mês de referência
-- (escolhido no calendário, ex: mes_referencia=2026-06-01, data_limite=2026-07-23).
-- Se não houver linha aqui para o mês, usa o dia-limite padrão da tabela
-- configuracao_prazo_avaliacao (aplicado sobre o mês seguinte ao mes_referencia).
CREATE TABLE IF NOT EXISTS prazos_avaliacao_mes (
    mes_referencia DATE PRIMARY KEY,
    data_limite    DATE NOT NULL,
    definido_por   TEXT,
    atualizado_em  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Pedido do supervisor ao coordenador para reabrir o prazo de um mês
-- (feito quando ele tenta avaliar um técnico e o prazo já encerrou).
CREATE TABLE IF NOT EXISTS solicitacoes_prazo_avaliacao (
    id             SERIAL PRIMARY KEY,
    supervisor     TEXT NOT NULL,
    tecnico        TEXT,              -- técnico que ele estava tentando avaliar (contexto do pedido)
    mes_referencia DATE NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pendente'
                       CHECK (status IN ('pendente', 'atendida', 'recusada')),
    criado_em      TIMESTAMP NOT NULL DEFAULT NOW(),
    atendida_em    TIMESTAMP,
    atendida_por   TEXT
);

CREATE INDEX IF NOT EXISTS idx_solicitacoes_status
    ON solicitacoes_prazo_avaliacao (status);
CREATE INDEX IF NOT EXISTS idx_solicitacoes_supervisor_mes
    ON solicitacoes_prazo_avaliacao (supervisor, mes_referencia);
