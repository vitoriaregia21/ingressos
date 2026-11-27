CREATE TABLE IF NOT EXISTS estoque (
 setor text PRIMARY KEY,
 inicial integer NOT NULL CHECK(inicial >= 0),
 disponivel integer NOT NULL CHECK(disponivel >= 0),
 reservado integer NOT NULL DEFAULT 0 CHECK(reservado >= 0),
 vendido integer NOT NULL DEFAULT 0 CHECK(vendido >= 0),
 CONSTRAINT estoque_invariante CHECK (inicial = disponivel + reservado + vendido)
);
INSERT INTO estoque(setor, inicial, disponivel) VALUES ('pista',50,50) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS reservas (
 id uuid PRIMARY KEY,
 setor text NOT NULL REFERENCES estoque(setor),
 cliente text NOT NULL,
 quantidade integer NOT NULL CHECK(quantidade > 0),
 estado text NOT NULL CHECK (estado IN ('em_reserva','confirmando','vendido','recusada','expirada')),
 criada_em timestamptz NOT NULL DEFAULT now(),
 expira_em timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS reservas_expiracao ON reservas(expira_em) WHERE estado = 'em_reserva';
CREATE TABLE IF NOT EXISTS pedidos (
 id uuid PRIMARY KEY,
 chave_idempotencia text UNIQUE NOT NULL,
 tipo text NOT NULL CHECK(tipo IN ('reservar','confirmar')),
 payload jsonb NOT NULL,
 status text NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','concluido','erro')),
 resultado jsonb,
 criado_em timestamptz NOT NULL DEFAULT now(),
 atualizado_em timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS outbox (
 id bigserial PRIMARY KEY,
 pedido_id uuid NOT NULL REFERENCES pedidos(id),
 publicado_em timestamptz,
 criado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_outbox_pendentes ON outbox(id) WHERE publicado_em IS NULL;
