-- ══════════════════════════════════════════════════════════
-- Marcação "não avaliar este técnico neste mês" + observação.
--
-- Usada quando o técnico aparece na lista do supervisor (por vínculo
-- vigente naquele mês), mas não deve ser avaliado — ex: não iniciou
-- atividade, estava afastado, em transição ou sob outra supervisão,
-- ou o supervisor não tem condições de avaliar. Não exige desvincular
-- nem descredenciar o técnico de verdade; fica só o registro do motivo.
--
-- Já é criada automaticamente no startup (ver rodar_migracoes_unicas em
-- app/repositorio.py) — este arquivo é só para quem preferir rodar via
-- migração manual, como as outras tabelas do projeto.
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS nao_avaliar_tecnico_mes (
    id             SERIAL PRIMARY KEY,
    supervisor     TEXT NOT NULL,
    tecnico        TEXT NOT NULL,
    mes_referencia DATE NOT NULL,
    observacao     TEXT NOT NULL,
    criado_por     TEXT NOT NULL,
    criado_em      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (supervisor, tecnico, mes_referencia)
);

CREATE INDEX IF NOT EXISTS idx_nao_avaliar_supervisor_mes
    ON nao_avaliar_tecnico_mes (supervisor, mes_referencia);
