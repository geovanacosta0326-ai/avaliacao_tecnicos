-- ══════════════════════════════════════════════════════════
-- VÍNCULO ÚNICO DO TÉCNICO (Gestão de Técnicos)
--
-- Substitui as duas tabelas separadas (tecnico_empresa e
-- tecnico_supervisor) por UM vínculo só, com todos os dados pedidos no
-- descritivo "Gestão de Técnicos": CPF, projeto, atividade, empresa,
-- CNPJ, supervisor responsável, datas de início/fim previsto, e
-- desvinculação (data real + motivo) separada da data prevista.
--
-- Nada é apagado: desvincular só preenche data_desvinculacao e
-- motivo_desvinculacao — o registro continua no histórico.
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS vinculo_tecnico (
    id                      SERIAL PRIMARY KEY,
    tecnico                 TEXT NOT NULL,      -- deve bater com tecnico_responsavel da base de visitas
    cpf                     TEXT,
    projeto                 TEXT,
    atividade               TEXT,
    empresa                 TEXT,
    cnpj_empresa            TEXT,
    supervisor              TEXT NOT NULL,      -- supervisor responsável por este vínculo

    data_inicio             DATE NOT NULL,
    data_fim_prevista       DATE,               -- prevista na criação do vínculo (pode ser nula = por prazo indeterminado)

    data_desvinculacao      DATE,               -- preenchida só quando o vínculo é encerrado de fato
    motivo_desvinculacao    TEXT,               -- obrigatório junto com data_desvinculacao

    criado_por              TEXT NOT NULL,
    criado_em               TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vinculo_tecnico_tecnico ON vinculo_tecnico (tecnico);
CREATE INDEX IF NOT EXISTS idx_vinculo_tecnico_supervisor ON vinculo_tecnico (supervisor);

-- No máximo 1 vínculo ATIVO por técnico por vez (data_desvinculacao IS NULL)
CREATE UNIQUE INDEX IF NOT EXISTS uq_vinculo_tecnico_ativo
    ON vinculo_tecnico (tecnico)
    WHERE data_desvinculacao IS NULL;
