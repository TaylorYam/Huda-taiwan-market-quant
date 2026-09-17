-- Derived Market Score persistence for model v0.1.
-- Source observations remain immutable in public.observations; this table
-- stores the exact calculation envelope used by a dashboard or backtest.

CREATE TABLE IF NOT EXISTS public.market_scores (
    id BIGSERIAL PRIMARY KEY,
    model_version TEXT NOT NULL,
    target_date DATE NOT NULL,
    as_of TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('available', 'unavailable')),
    score NUMERIC,
    direction TEXT,
    reason TEXT,
    calculation_hash TEXT NOT NULL,
    factor_scores_json JSONB NOT NULL,
    observation_identities_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT market_scores_value_state CHECK (
        (status = 'available' AND score IS NOT NULL AND score >= 0 AND score <= 100 AND direction IS NOT NULL)
        OR
        (status = 'unavailable' AND score IS NULL AND direction IS NULL)
    ),
    CONSTRAINT market_scores_calculation_identity
        UNIQUE (model_version, target_date, calculation_hash)
);

CREATE INDEX IF NOT EXISTS market_scores_latest_date
    ON public.market_scores (target_date DESC, id DESC);

ALTER TABLE public.market_scores ENABLE ROW LEVEL SECURITY;
