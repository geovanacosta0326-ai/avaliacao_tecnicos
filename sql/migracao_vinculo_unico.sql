-- ══════════════════════════════════════════════════════════
-- MIGRAÇÃO — rodar UMA VEZ, depois de criar vinculo_tecnico
-- (schema_vinculo_tecnico.sql).
--
-- Junta os vínculos ativos de tecnico_supervisor (obrigatório, pois
-- vinculo_tecnico exige supervisor) com os dados de empresa/CPF de
-- tecnico_empresa (se existirem para aquele técnico). Técnicos que só
-- tinham vínculo de empresa mas nenhum supervisor ativo NÃO são
-- migrados automaticamente — precisam ser cadastrados na tela nova,
-- já que "supervisor responsável" é obrigatório no vínculo único.
-- ══════════════════════════════════════════════════════════
INSERT INTO vinculo_tecnico
    (tecnico, cpf, empresa, cnpj_empresa, supervisor, data_inicio, criado_por)
SELECT
    ts.tecnico,
    te.cpf,
    te.empresa,
    te.cnpj_empresa,
    ts.supervisor,
    ts.mes_inicio,
    'migração automática'
FROM tecnico_supervisor ts
LEFT JOIN tecnico_empresa te
    ON te.tecnico = ts.tecnico AND te.data_fim IS NULL
WHERE ts.mes_fim IS NULL
ON CONFLICT (tecnico) WHERE data_desvinculacao IS NULL DO NOTHING;

-- Tabelas antigas viram backup — não apaga nada, só sai do caminho.
-- O sistema, a partir de agora, só lê/escreve em vinculo_tecnico.
ALTER TABLE IF EXISTS tecnico_empresa RENAME TO tecnico_empresa_legado;
ALTER TABLE IF EXISTS tecnico_supervisor RENAME TO tecnico_supervisor_legado;
