defmodule FleetAdmin.Repo.Migrations.CreateAuditEvents do
  use Ecto.Migration

  def change do
    create table(:audit_events) do
      add :run_id, references(:runs, on_delete: :nilify_all)
      add :ts, :utc_datetime
      add :severity, :string
      add :action, :string
      add :detail, :string
      add :container, :string

      timestamps(type: :utc_datetime)
    end

    create index(:audit_events, [:run_id])
    create index(:audit_events, [:severity])
  end
end
