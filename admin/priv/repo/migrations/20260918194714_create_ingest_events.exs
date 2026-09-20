defmodule FleetAdmin.Repo.Migrations.CreateIngestEvents do
  use Ecto.Migration

  def change do
    create table(:ingest_events) do
      add :event, :string, null: false
      add :status, :string
      add :source, :string
      add :webhook_event, :string
      add :delivery, :string
      add :actionable, :boolean
      add :issue_key, :string
      add :project, :string
      add :repo, :string
      add :reason, :string
      add :detail, :text
      add :payload, :text

      timestamps(type: :utc_datetime)
    end

    create index(:ingest_events, [:event])
    create index(:ingest_events, [:source])
    create index(:ingest_events, [:status])
  end
end
