defmodule FleetAdmin.Repo.Migrations.CreateRuns do
  use Ecto.Migration

  def change do
    create table(:runs) do
      add :external_id, :string, null: false
      add :source, :string
      add :issue_key, :string
      add :repo, :string
      add :branch, :string
      add :commit, :string
      add :pr_url, :string
      add :status, :string, null: false, default: "running"
      add :tool, :string
      add :platform, :string
      add :cost, :float
      add :error, :string
      add :started_at, :utc_datetime
      add :finished_at, :utc_datetime

      timestamps(type: :utc_datetime)
    end

    create unique_index(:runs, [:external_id])
    create index(:runs, [:status])
    create index(:runs, [:issue_key])
  end
end
