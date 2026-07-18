-- ══════════════════════════════════════════════════════════
-- Tabela de login dos supervisores
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS usuarios_supervisores (
    id                      SERIAL PRIMARY KEY,
    supervisor              TEXT NOT NULL UNIQUE,   -- deve bater exatamente com supervisor_atual
    login                   TEXT NOT NULL UNIQUE,
    senha_hash              TEXT NOT NULL,
    tipo                    TEXT NOT NULL DEFAULT 'supervisor'
                                CHECK (tipo IN ('supervisor', 'coordenador')),
    precisa_trocar_senha    BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em               TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Se a tabela já existia sem a coluna "tipo", isso adiciona sem dar erro:
ALTER TABLE usuarios_supervisores
    ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'supervisor';

-- ══════════════════════════════════════════════════════════
-- Tabela de avaliações mensais dos técnicos
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS avaliacoes_tecnicos (
    id                          SERIAL PRIMARY KEY,
    supervisor                  TEXT NOT NULL,
    tecnico                     TEXT NOT NULL,
    mes_referencia              DATE NOT NULL,   -- sempre dia 1 do mês avaliado (ex: 2026-06-01)

    -- Bloco 2 — Desempenho Metodológico
    p1_dominio_metodologia      SMALLINT,   -- nota 5-10
    p2_aplica_metodologia       SMALLINT,   -- nota 5-10
    p3_horas_visita             SMALLINT,   -- nota 5-10 (convertida da escolha de faixa de horas)
    p4_planejamento_participativo TEXT,     -- Sim / Não / Outro
    p5_analise_swot             TEXT,       -- texto livre

    -- Bloco 3 — Desempenho do SISATEG
    p6_dominio_offline          SMALLINT,
    p7_dominio_online           SMALLINT,
    p8_dominio_mobile           SMALLINT,
    p9_relatorio_mensal         SMALLINT,

    -- Bloco 4 — Desempenho das Orientações
    p10_alia_tecnica_gerencial      SMALLINT,
    p11_clareza_recomendacoes       SMALLINT,
    p12_pertinencia_recomendacoes   SMALLINT,
    p13_orientacoes_producao        TEXT,   -- Sim / Não / Outro
    p14_dpi                         SMALLINT,

    -- Bloco 5 — Desempenho do Planejamento
    p15_qualidade_swot          SMALLINT,
    p16_qualidade_metas         SMALLINT,
    p17_qualidade_planos_acao   SMALLINT,
    p18_planejamento_atende     SMALLINT,
    p19_capacidade_planejamento SMALLINT,

    -- Bloco 7 — Desempenho Comportamental (inclui articulação/rede)
    p20_resolucao_problemas          SMALLINT,
    p21_lideranca_equipe             SMALLINT,
    p22_articulacao_produtores       SMALLINT,
    p23_participacao_capacitacoes    SMALLINT,

    -- Bloco 8 — Avaliação Qualitativa
    p24_analise_tecnica         TEXT,
    p25_analise_gerencial       TEXT,

    media_final                 NUMERIC(4,2),   -- calculada no momento do envio
    data_avaliacao               TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (supervisor, tecnico, mes_referencia)  -- trava: 1 avaliação por técnico/mês
);

CREATE INDEX IF NOT EXISTS idx_avaliacoes_supervisor ON avaliacoes_tecnicos (supervisor);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_tecnico ON avaliacoes_tecnicos (tecnico);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_mes ON avaliacoes_tecnicos (mes_referencia);

-- ══════════════════════════════════════════════════════════
-- CPF do técnico, guardado junto do vínculo com a empresa
-- (pode mudar de valor se um vínculo novo for cadastrado com
-- um CPF diferente, mas normalmente se repete a cada vínculo)
-- ══════════════════════════════════════════════════════════
ALTER TABLE tecnico_empresa ADD COLUMN IF NOT EXISTS cpf TEXT;
