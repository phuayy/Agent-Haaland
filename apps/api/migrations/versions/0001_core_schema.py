"""core schema — incidents, the append-only hash-chained event log, evidence,
deployments, ai_analyses, redaction_maps, remediations, approvals,
notifications, postmortems, services, users.

Per docs/03-data-model.md: this revision, and the incident_events table and
its append-only trigger specifically, are never altered after merge. If the
shape must change, version it (incident_events_v2) with a documented cutover
— altering this file would change hash inputs and break verification of
every previously recorded event.

Revision ID: 0001
Revises:
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.execute("CREATE TYPE severity AS ENUM ('P1','P2','P3','P4')")
    op.execute(
        """
        CREATE TYPE incident_status AS ENUM (
          'detected','enriching','triaging','triaged_low','diagnosing',
          'awaiting_approval','escalated','approved','rejected',
          'remediating','verifying','documenting','closed','failed'
        )
        """
    )
    op.execute("CREATE TYPE actor_type AS ENUM ('system','ai','human','integration')")

    op.execute(
        """
        CREATE TABLE services (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          name          text NOT NULL UNIQUE,
          repo_full_name text,
          tier          smallint NOT NULL DEFAULT 2,
          owner_team    text,
          slack_channel text,
          pagerduty_service_id text,
          runbook_url   text,
          slo_p99_ms    integer,
          metadata      jsonb NOT NULL DEFAULT '{}',
          created_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE service_dependencies (
          upstream_id   uuid NOT NULL REFERENCES services(id) ON DELETE CASCADE,
          downstream_id uuid NOT NULL REFERENCES services(id) ON DELETE CASCADE,
          kind          text NOT NULL,
          critical      boolean NOT NULL DEFAULT false,
          PRIMARY KEY (upstream_id, downstream_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE users (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          email         citext NOT NULL UNIQUE,
          display_name  text NOT NULL,
          slack_user_id text UNIQUE,
          github_login  text UNIQUE,
          role          text NOT NULL DEFAULT 'engineer',
          is_active     boolean NOT NULL DEFAULT true,
          created_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE incidents (
          id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          reference         text NOT NULL UNIQUE,
          title             text NOT NULL,
          status            incident_status NOT NULL DEFAULT 'detected',
          severity          severity,
          severity_confidence real,
          primary_service_id uuid REFERENCES services(id),
          affected_service_ids text[] NOT NULL DEFAULT '{}',
          suspected_deployment_id uuid,
          repo_full_name    text,
          base_ref          text,

          detected_at       timestamptz NOT NULL DEFAULT now(),
          acknowledged_at   timestamptz,
          triaged_at        timestamptz,
          diagnosed_at      timestamptz,
          approved_at       timestamptz,
          recovered_at      timestamptz,
          closed_at         timestamptz,

          root_cause_summary text,
          closed_reason     text,
          chain_head_hash   bytea,
          metadata          jsonb NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_incidents_status ON incidents (status) "
        "WHERE status NOT IN ('closed','failed')"
    )
    op.execute("CREATE INDEX ix_incidents_detected ON incidents (detected_at DESC)")

    op.execute(
        """
        CREATE TABLE deployments (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          service_id    uuid NOT NULL REFERENCES services(id),
          provider      text NOT NULL DEFAULT 'github',
          external_id   text NOT NULL,
          commit_sha    text NOT NULL,
          previous_sha  text,
          ref           text,
          author_login  text,
          pr_number     integer,
          environment   text NOT NULL DEFAULT 'production',
          status        text NOT NULL,
          changed_files text[],
          diff_summary  jsonb,
          deployed_at   timestamptz NOT NULL,
          UNIQUE (provider, external_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_deployments_service_time ON deployments (service_id, deployed_at DESC)")

    op.execute(
        "ALTER TABLE incidents ADD CONSTRAINT fk_incidents_suspected_deployment "
        "FOREIGN KEY (suspected_deployment_id) REFERENCES deployments(id)"
    )

    # --- incident_events: the compliance artefact -------------------------
    op.execute(
        """
        CREATE TABLE incident_events (
          id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          incident_id   uuid NOT NULL REFERENCES incidents(id) ON DELETE RESTRICT,
          seq           integer NOT NULL,
          event_type    text NOT NULL,
          actor_type    actor_type NOT NULL,
          actor_id      text,
          actor_label   text NOT NULL,
          summary       text NOT NULL,
          payload       jsonb NOT NULL DEFAULT '{}',
          occurred_at   timestamptz NOT NULL DEFAULT now(),

          prev_hash     bytea,
          hash          bytea NOT NULL,

          UNIQUE (incident_id, seq)
        )
        """
    )
    op.execute("CREATE INDEX ix_events_incident_seq ON incident_events (incident_id, seq)")
    op.execute("CREATE INDEX ix_events_type ON incident_events (event_type)")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_event_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'incident_events is append-only (attempted % on id=%)',
            TG_OP, COALESCE(OLD.id, NEW.id);
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_events_append_only
          BEFORE UPDATE OR DELETE ON incident_events
          FOR EACH ROW EXECUTE FUNCTION reject_event_mutation()
        """
    )

    op.execute(
        """
        CREATE TABLE evidence (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          incident_id   uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
          kind          text NOT NULL,
          source        text NOT NULL,
          source_ref    text,
          window_start  timestamptz,
          window_end    timestamptz,
          content       jsonb NOT NULL,
          content_raw_ref text,
          relevance     real,
          collected_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_evidence_incident_kind ON evidence (incident_id, kind)")

    op.execute(
        """
        CREATE TABLE ai_analyses (
          id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          incident_id       uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
          stage             text NOT NULL,
          provider          text NOT NULL,
          model             text NOT NULL,
          prompt_version    text NOT NULL,
          prompt_hash       bytea NOT NULL,
          redaction_map_id  uuid,
          request_payload   jsonb NOT NULL,
          response_payload  jsonb NOT NULL,
          stop_reason       text,
          input_tokens      integer,
          output_tokens     integer,
          cache_read_tokens integer,
          cache_write_tokens integer,
          cost_usd          numeric(10,6),
          latency_ms        integer,
          created_at        timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_analyses_incident ON ai_analyses (incident_id, created_at)")

    op.execute(
        """
        CREATE TABLE redaction_maps (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          incident_id   uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
          vault_key     text NOT NULL,
          entity_counts jsonb NOT NULL,
          recogniser_versions jsonb NOT NULL,
          created_at    timestamptz NOT NULL DEFAULT now(),
          expires_at    timestamptz NOT NULL
        )
        """
    )

    op.execute(
        "ALTER TABLE ai_analyses ADD CONSTRAINT fk_analyses_redaction_map "
        "FOREIGN KEY (redaction_map_id) REFERENCES redaction_maps(id)"
    )

    op.execute(
        """
        CREATE TABLE remediations (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          incident_id   uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
          strategy      text NOT NULL,
          rationale     text NOT NULL,
          risk_notes    text,
          repo_full_name text NOT NULL,
          branch_name   text NOT NULL,
          base_sha      text NOT NULL,
          patch         text NOT NULL,
          attempt_count integer NOT NULL DEFAULT 1,
          pr_number     integer,
          pr_url        text,
          status        text NOT NULL DEFAULT 'pending',
          created_at    timestamptz NOT NULL DEFAULT now(),
          resolved_at   timestamptz
        )
        """
    )

    op.execute(
        """
        CREATE TABLE approvals (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          remediation_id uuid NOT NULL REFERENCES remediations(id) ON DELETE CASCADE,
          user_id       uuid REFERENCES users(id),
          actor_label   text NOT NULL,
          decision      text NOT NULL,
          reason        text,
          channel       text NOT NULL,
          decided_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_approvals_remediation ON approvals (remediation_id)")

    op.execute(
        """
        CREATE TABLE notifications (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          incident_id   uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
          channel       text NOT NULL,
          target        text NOT NULL,
          external_ref  text,
          status        text NOT NULL,
          payload       jsonb NOT NULL,
          sent_at       timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE postmortems (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          incident_id   uuid NOT NULL UNIQUE REFERENCES incidents(id) ON DELETE CASCADE,
          version       integer NOT NULL DEFAULT 1,
          markdown      text NOT NULL,
          pdf_ref       text,
          generated_at  timestamptz NOT NULL DEFAULT now(),
          approved_by   uuid REFERENCES users(id),
          approved_at   timestamptz
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS postmortems")
    op.execute("DROP TABLE IF EXISTS notifications")
    op.execute("DROP TABLE IF EXISTS approvals")
    op.execute("DROP TABLE IF EXISTS remediations")
    op.execute("DROP TABLE IF EXISTS redaction_maps")
    op.execute("DROP TABLE IF EXISTS ai_analyses")
    op.execute("DROP TABLE IF EXISTS evidence")
    op.execute("DROP TRIGGER IF EXISTS trg_events_append_only ON incident_events")
    op.execute("DROP FUNCTION IF EXISTS reject_event_mutation")
    op.execute("DROP TABLE IF EXISTS incident_events")
    op.execute("ALTER TABLE incidents DROP CONSTRAINT IF EXISTS fk_incidents_suspected_deployment")
    op.execute("DROP TABLE IF EXISTS deployments")
    op.execute("DROP TABLE IF EXISTS incidents")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS service_dependencies")
    op.execute("DROP TABLE IF EXISTS services")
    op.execute("DROP TYPE IF EXISTS actor_type")
    op.execute("DROP TYPE IF EXISTS incident_status")
    op.execute("DROP TYPE IF EXISTS severity")
