-- ══════════════════════════════════════════════════════════
-- Tabelas MESTRAS de supervisores e técnicos.
--
-- Substituem a lógica de "derivar tudo da tabela de visitas por nome"
-- (que sofre com atraso de atualização e diferenças de acento/espaço).
-- Agora supervisor e técnico são cadastros próprios, com ID estável
-- (o técnico usa o MESMO id_tecnico_responsavel da tabela de visitas),
-- e só o coordenador pode ativar/desativar.
-- ══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS supervisores (
    id             SERIAL PRIMARY KEY,
    nome           TEXT NOT NULL UNIQUE,
    ativo          BOOLEAN NOT NULL DEFAULT TRUE,

    -- Dados cadastrais complementares, preenchidos pelo coordenador.
    rg                     TEXT,
    cpf                    TEXT,
    contato                TEXT,
    empresa                TEXT,
    cnpj_empresa           TEXT,
    data_inicio_vinculo    DATE,
    data_fim_vinculo       DATE,

    -- Motivo/data da desativação (preenchido pelo coordenador ao desativar,
    -- igual ao desvínculo de técnico — limpo automaticamente ao reativar).
    motivo_desativacao     TEXT,
    data_desativacao       DATE,

    criado_em      TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Garante as colunas novas mesmo se a tabela já tiver sido criada antes.
ALTER TABLE supervisores ADD COLUMN IF NOT EXISTS rg TEXT;
ALTER TABLE supervisores ADD COLUMN IF NOT EXISTS cpf TEXT;
ALTER TABLE supervisores ADD COLUMN IF NOT EXISTS contato TEXT;
ALTER TABLE supervisores ADD COLUMN IF NOT EXISTS empresa TEXT;
ALTER TABLE supervisores ADD COLUMN IF NOT EXISTS cnpj_empresa TEXT;
ALTER TABLE supervisores ADD COLUMN IF NOT EXISTS motivo_desativacao TEXT;
ALTER TABLE supervisores ADD COLUMN IF NOT EXISTS data_desativacao DATE;
ALTER TABLE supervisores ADD COLUMN IF NOT EXISTS data_inicio_vinculo DATE;
ALTER TABLE supervisores ADD COLUMN IF NOT EXISTS data_fim_vinculo DATE;

CREATE TABLE IF NOT EXISTS tecnicos (
    id_tecnico_responsavel BIGINT PRIMARY KEY,
    nome                   TEXT NOT NULL,
    ativo                  BOOLEAN NOT NULL DEFAULT TRUE,
    primeira_visita        DATE,
    ultima_visita          DATE,

    -- Dados cadastrais complementares, preenchidos pelo coordenador
    -- (não vêm da consulta de visitas, são digitados manualmente).
    rg                     TEXT,
    cpf                    TEXT,
    contato                TEXT,
    empresa                TEXT,
    cnpj_empresa           TEXT,
    endereco               TEXT,
    municipio              TEXT,
    data_inicio_vinculo    DATE,
    data_fim_vinculo       DATE,

    criado_em              TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em          TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Garante as colunas novas mesmo se a tabela já tiver sido criada antes
-- (rodar essa migração de novo nunca quebra nada, só completa o que falta).
ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS rg TEXT;
ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS cpf TEXT;
ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS contato TEXT;
ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS empresa TEXT;
ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS cnpj_empresa TEXT;
ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS endereco TEXT;
ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS municipio TEXT;
ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS data_inicio_vinculo DATE;
ALTER TABLE tecnicos ADD COLUMN IF NOT EXISTS data_fim_vinculo DATE;

CREATE INDEX IF NOT EXISTS idx_tecnicos_nome ON tecnicos (nome);
CREATE INDEX IF NOT EXISTS idx_tecnicos_ativo ON tecnicos (ativo);
CREATE INDEX IF NOT EXISTS idx_supervisores_ativo ON supervisores (ativo);

-- Um técnico pode atender mais de uma combinação projeto+atividade ao
-- mesmo tempo (ex: bovinocultura numa propriedade, ovinocultura em
-- outra) — por isso essa tabela pode ter VÁRIAS linhas pro mesmo
-- id_tecnico_responsavel, uma por combinação. Serve pra contar
-- propriedades atendidas por atividade, igual ao ranking objetivo.
-- Não guarda supervisor de propósito — a avaliação continua sendo por
-- TÉCNICO (pessoa), não por atividade, pelo menos por enquanto.
CREATE TABLE IF NOT EXISTS tecnico_atividades (
    id                      SERIAL PRIMARY KEY,
    id_tecnico_responsavel  BIGINT NOT NULL REFERENCES tecnicos(id_tecnico_responsavel),
    projeto                 TEXT,
    atividade               TEXT,
    propriedades_atendidas  INT NOT NULL DEFAULT 0,
    primeira_visita         DATE,
    ultima_visita           DATE,
    atualizado_em           TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (id_tecnico_responsavel, projeto, atividade)
);

CREATE INDEX IF NOT EXISTS idx_tecnico_atividades_tecnico ON tecnico_atividades (id_tecnico_responsavel);
