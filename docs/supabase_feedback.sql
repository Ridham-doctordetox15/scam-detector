-- Feedback table for POST /feedback (Phase 9). Run once in Supabase: SQL Editor -> New query -> Run.
--
-- Privacy: this table never holds message text, screenshot text, URLs, IPs or user identifiers.
-- A row is: which prediction (random UUID), whether the user said it was correct, and the
-- non-text labels of that prediction.
--
-- Access: Row Level Security is ON with NO policies, and the public roles have no privileges,
-- so the anon/publishable key can neither read nor write. Only the API server's SECRET key
-- (sb_secret_..., role service_role, which bypasses RLS) can write, via the explicit GRANT
-- below. Never put the secret key in a frontend.
--
-- Already ran an earlier version of this file? Run just the GRANT line near the end.

create table if not exists public.feedback (
    id                   bigint generated always as identity primary key,
    prediction_id        uuid        not null unique,
    user_verdict         text        not null check (user_verdict in ('correct', 'incorrect')),
    predicted_verdict    text        not null check (predicted_verdict in ('safe', 'suspicious', 'scam')),
    predicted_risk_level text        not null check (predicted_risk_level in ('low', 'medium', 'high')),
    input_type           text        not null check (input_type in ('text', 'image')),
    classifier_model     text        not null check (char_length(classifier_model) <= 64),
    explainer_path       text        not null check (explainer_path in ('groq', 'gemini', 'template')),
    matched_pattern      text                 check (char_length(matched_pattern) <= 128),
    created_at           timestamptz not null default now()
);

comment on table public.feedback is
    'User feedback on scam-detector predictions. No message text or personal data by design.';

alter table public.feedback enable row level security;
revoke all on table public.feedback from anon, authenticated;
-- The secret key acts as the service_role role. It bypasses RLS, but still needs table
-- privileges, which new projects no longer grant by default. INSERT + UPDATE are needed for
-- the upsert on prediction_id; SELECT lets you (and the verification check) read rows back.
grant select, insert, update on table public.feedback to service_role;

-- Useful query once feedback arrives: agreement rate per verdict.
-- select predicted_verdict,
--        count(*) as n,
--        round(avg((user_verdict = 'correct')::int) * 100, 1) as pct_marked_correct
-- from public.feedback group by predicted_verdict order by n desc;
