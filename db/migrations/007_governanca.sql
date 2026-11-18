-- =====================================================================
-- 007 - Governanca: linhagem, quarentena e metricas de qualidade
--
-- Principio: dado ruim NAO e descartado silenciosamente. Ele vai para
-- quarentena com um reason_code rastreavel. Isso permite:
--   1. o dono ver "120 cupons nao entraram hoje" em vez de um numero
--      de venda que simplesmente encolheu sem explicacao;
--   2. o time corrigir a causa na origem;
--   3. o relatorio provar que o controle existe (evidencia).
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- Lote de carga: unidade de auditoria e linhagem
--
-- Todo registro carregado guarda lote_carga_id. Assim, se um lote
-- estiver corrupto, da para rastrear e reverter exatamente ele.
-- ---------------------------------------------------------------------
CREATE TABLE gov.lote_carga (
    lote_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origem           TEXT NOT NULL,           -- 'PDV_CSV', 'PLANILHA_ESTOQUE', 'NFE_XML'
    arquivo          TEXT,
    hash_arquivo     TEXT,                    -- sha256: detecta reimportacao
    data_referencia  DATE,
    iniciado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalizado_em    TIMESTAMPTZ,
    status           TEXT NOT NULL DEFAULT 'EM_ANDAMENTO',
    linhas_lidas     INTEGER NOT NULL DEFAULT 0,
    linhas_aceitas   INTEGER NOT NULL DEFAULT 0,
    linhas_rejeitadas INTEGER NOT NULL DEFAULT 0,
    mensagem         TEXT,

    CONSTRAINT lote_status_ck CHECK (status IN ('EM_ANDAMENTO','CONCLUIDO','FALHOU','PARCIAL')),
    CONSTRAINT lote_contagem_ck CHECK (linhas_aceitas + linhas_rejeitadas <= linhas_lidas)
);

COMMENT ON TABLE gov.lote_carga IS
  'Auditoria de cada execucao de carga. lote_carga_id e a chave de linhagem de todo dado.';
COMMENT ON COLUMN gov.lote_carga.hash_arquivo IS
  'SHA-256 do arquivo. Reimportar o mesmo arquivo e detectavel e idempotente.';

-- ---------------------------------------------------------------------
-- Catalogo de regras de qualidade
--
-- As regras ficam em tabela (nao em codigo) por tres motivos:
--   1. o relatorio pode listar as regras direto do banco;
--   2. a severidade muda sem deploy;
--   3. a metrica de qualidade por loja e calculada a partir daqui.
-- ---------------------------------------------------------------------
CREATE TABLE gov.regra_qualidade (
    regra_id      INTEGER PRIMARY KEY,
    codigo        TEXT NOT NULL UNIQUE,       -- 'DQ001'
    dimensao      TEXT NOT NULL,              -- completude, unicidade, ...
    descricao     TEXT NOT NULL,
    severidade    TEXT NOT NULL,              -- critica, alta, media, baixa
    acao          TEXT NOT NULL,              -- rejeitar, quarentena, corrigir, alertar
    expressao_sql TEXT,
    ativa         BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT dq_dimensao_ck CHECK (dimensao IN (
        'completude','unicidade','consistencia','validade','acuracidade','atualidade','conformidade'
    )),
    CONSTRAINT dq_severidade_ck CHECK (severidade IN ('critica','alta','media','baixa')),
    CONSTRAINT dq_acao_ck CHECK (acao IN ('rejeitar','quarentena','corrigir','alertar'))
);

COMMENT ON TABLE gov.regra_qualidade IS
  'Catalogo de regras de qualidade. A dimensao segue as 6 dimensoes classicas.';

-- ---------------------------------------------------------------------
-- Quarentena generica
--
-- Uma unica tabela para todos os tipos de rejeicao, com o payload
-- original guardado em JSONB. Vantagem: nao precisamos de uma tabela
-- de quarentena por entidade, e o schema do payload varia sem ALTER.
-- Custo: consulta sobre JSONB e menos tipada - aceitavel, porque
-- quarentena e lida por humano e por relatorio, nao por transacao.
-- ---------------------------------------------------------------------
CREATE TABLE gov.quarentena (
    quarentena_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id       BIGINT NOT NULL REFERENCES gov.lote_carga(lote_id) ON DELETE CASCADE,
    regra_id      INTEGER NOT NULL REFERENCES gov.regra_qualidade(regra_id) ON DELETE RESTRICT,
    entidade      TEXT NOT NULL,              -- 'venda','item_venda','estoque_snapshot'
    chave_registro TEXT,                      -- identificacao do registro ruim
    payload       JSONB NOT NULL,             -- linha original completa
    motivo        TEXT NOT NULL,              -- mensagem legivel
    detectado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolvido    BOOLEAN NOT NULL DEFAULT FALSE,
    resolvido_em TIMESTAMPTZ,
    resolvido_por TEXT,

    CONSTRAINT quarentena_resolucao_ck CHECK (
        (resolvido = FALSE AND resolvido_em IS NULL) OR
        (resolvido = TRUE  AND resolvido_em IS NOT NULL)
    )
);

COMMENT ON TABLE gov.quarentena IS
  'Registros rejeitados com reason_code. Nunca descarte silencioso.';

CREATE INDEX ix_quarentena_lote ON gov.quarentena (lote_id);
CREATE INDEX ix_quarentena_regra ON gov.quarentena (regra_id);
CREATE INDEX ix_quarentena_pendente ON gov.quarentena (detectado_em)
    WHERE resolvido = FALSE;
-- Busca por conteudo do payload (ex.: achar todas as rejeicoes de um EAN).
CREATE INDEX ix_quarentena_payload ON gov.quarentena USING gin (payload jsonb_path_ops);

-- ---------------------------------------------------------------------
-- Metrica de qualidade por lote
--
-- Calculada ao final de cada carga. E o que alimenta o "selo de
-- confianca" do produto: a sugestao de compra so e exibida como
-- confiavel se o score da loja passar do limiar.
-- ---------------------------------------------------------------------
CREATE TABLE gov.metrica_qualidade (
    metrica_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id       BIGINT REFERENCES gov.lote_carga(lote_id) ON DELETE CASCADE,
    loja_id       BIGINT REFERENCES prata.loja(loja_id) ON DELETE CASCADE,
    data_ref      DATE NOT NULL,
    dimensao      TEXT NOT NULL,
    total_registros     BIGINT NOT NULL,
    registros_ok        BIGINT NOT NULL,
    registros_problema  BIGINT NOT NULL,
    score_pct     NUMERIC(6,3) GENERATED ALWAYS AS (
        CASE WHEN total_registros > 0
             THEN round(registros_ok::numeric / total_registros * 100, 3)
             ELSE NULL END
    ) STORED,
    calculado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT metrica_dimensao_ck CHECK (dimensao IN (
        'completude','unicidade','consistencia','validade','acuracidade','atualidade','conformidade'
    )),
    CONSTRAINT metrica_soma_ck CHECK (registros_ok + registros_problema = total_registros)
);

COMMENT ON TABLE gov.metrica_qualidade IS
  'Score de qualidade por lote/loja/dimensao. Alimenta o selo de confianca exibido no produto.';

CREATE INDEX ix_metrica_loja_data ON gov.metrica_qualidade (loja_id, data_ref);

-- ---------------------------------------------------------------------
-- Log de auditoria (LGPD + seguranca)
--
-- Quem alterou o que, quando. Obrigatorio para dado de negocio e
-- exigido pela secao 4.5 do edital (controle de acesso e riscos).
-- ---------------------------------------------------------------------
CREATE TABLE gov.auditoria (
    auditoria_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ocorrido_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    usuario      TEXT NOT NULL DEFAULT current_user,
    acao         TEXT NOT NULL,
    entidade     TEXT NOT NULL,
    chave        TEXT,
    dados_antes  JSONB,
    dados_depois JSONB,
    ip           INET,

    CONSTRAINT auditoria_acao_ck CHECK (acao IN ('INSERT','UPDATE','DELETE','SELECT_SENSIVEL','LOGIN','EXPORT'))
);

COMMENT ON TABLE gov.auditoria IS
  'Trilha de auditoria. Base para LGPD art. 37 (registro de operacoes).';

CREATE INDEX ix_auditoria_entidade ON gov.auditoria (entidade, chave);
CREATE INDEX ix_auditoria_data ON gov.auditoria (ocorrido_em DESC);

-- ---------------------------------------------------------------------
-- Carga inicial do catalogo de regras
--
-- Cada regra tem codigo estavel (DQnnn) para ser citada no relatorio
-- e nos logs. A coluna expressao_sql documenta a verificacao; a
-- implementacao executavel esta em src/validate.py e tests/.
-- ---------------------------------------------------------------------
INSERT INTO gov.regra_qualidade (regra_id, codigo, dimensao, descricao, severidade, acao) VALUES
 (1,'DQ001','completude','Venda sem data, loja ou numero de cupom','critica','rejeitar'),
 (2,'DQ002','completude','Item de venda sem produto identificado','critica','rejeitar'),
 (3,'DQ003','completude','Snapshot de estoque faltante em dia de loja aberta','alta','quarentena'),
 (4,'DQ004','unicidade','Cupom duplicado (loja, data, serie, numero)','critica','rejeitar'),
 (5,'DQ005','unicidade','Item duplicado dentro do mesmo cupom','alta','rejeitar'),
 (6,'DQ006','unicidade','EAN duplicado no cadastro de produto','critica','quarentena'),
 (7,'DQ007','consistencia','valor_liquido diferente de valor_bruto - desconto','critica','rejeitar'),
 (8,'DQ008','consistencia','Soma dos itens difere do total do cupom','critica','rejeitar'),
 (9,'DQ009','consistencia','Equacao de estoque nao fecha (inicio+entradas+saidas+ajustes <> fim)','critica','quarentena'),
 (10,'DQ010','consistencia','Saida de estoque sem venda ou movimentacao correspondente','alta','alertar'),
 (11,'DQ011','validade','EAN-13 com digito verificador incorreto','critica','quarentena'),
 (12,'DQ012','validade','Quantidade negativa ou zero em item de venda','alta','rejeitar'),
 (13,'DQ013','validade','Data de venda no futuro','alta','rejeitar'),
 (14,'DQ014','validade','Preco unitario negativo ou zero','alta','rejeitar'),
 (15,'DQ015','validade','UF inexistente no cadastro de loja','media','quarentena'),
 (16,'DQ016','acuracidade','Divergencia entre estoque do sistema e contagem fisica acima de 5%','alta','alertar'),
 (17,'DQ017','atualidade','Carga do PDV nao concluida ate 06:00 do dia seguinte','alta','alertar'),
 (18,'DQ018','atualidade','Dia de loja aberta sem nenhum registro de venda','media','quarentena'),
 (19,'DQ019','conformidade','Registro contendo CPF ou dado pessoal nao permitido','critica','rejeitar'),
 (20,'DQ020','consistencia','Cupom marcado como concluido com data de cancelamento','media','corrigir'),
 -- DQ021 e uma pseudo-regra: registra registros rejeitados por CASCATA,
 -- isto e, porque a entidade pai foi rejeitada no mesmo lote (item cujo
 -- produto teve EAN invalido, por exemplo). Nao e defeito do proprio
 -- registro. Separa-la e essencial para que as metricas de recall por
 -- regra medam a eficacia da REGRA e nao o efeito em cascata.
 (21,'DQ021','consistencia','Registro rejeitado por dependencia com entidade rejeitada (cascata)','alta','quarentena');

COMMENT ON TABLE gov.regra_qualidade IS
  'Catalogo DQ001..DQ020. Codigos citados no relatorio e nos logs de carga.';

COMMIT;
