"""
Consulta consolidada: técnicos que já têm ao menos uma visita registrada,
com primeira/última visita (vindas de acompanhamento_mensal_visitas) e o
vínculo de empresa ATIVO no momento (vindo de tecnico_empresa, se existir).

Técnico sem nenhuma linha em tecnico_empresa ainda aparece na lista —
só com os campos de empresa em branco (LEFT JOIN), esperando o
coordenador completar.
"""

QUERY_TECNICOS_CONSOLIDADO = """
SELECT
    v.tecnico,
    v.primeira_visita,
    v.ultima_visita,
    e.id                  AS vinculo_id,
    e.empresa,
    e.cnpj_empresa,
    e.data_inicio,
    e.data_fim,
    e.motivo_desvinculo,
    CASE WHEN e.data_fim IS NULL AND e.id IS NOT NULL
         THEN TRUE ELSE FALSE END AS ativo
FROM (
    SELECT
        tecnico_responsavel AS tecnico,
        MIN(dt_visita)      AS primeira_visita,
        MAX(dt_visita)      AS ultima_visita
    FROM public.acompanhamento_mensal_visitas
    WHERE tecnico_responsavel IS NOT NULL
    GROUP BY tecnico_responsavel
) v
LEFT JOIN tecnico_empresa e
    ON e.tecnico = v.tecnico
    AND e.data_fim IS NULL   -- pega só o vínculo ativo atual, se houver
ORDER BY v.tecnico;
"""

# Histórico completo de vínculos de um técnico específico (para a tela de detalhe)
QUERY_HISTORICO_TECNICO_EMPRESA = """
SELECT empresa, cnpj_empresa, data_inicio, data_fim, motivo_desvinculo, criado_por
FROM tecnico_empresa
WHERE tecnico = :tecnico
ORDER BY data_inicio DESC;
"""
