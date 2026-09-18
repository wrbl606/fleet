defmodule FleetAdmin.Repo.Migrations.CreateIterations do
  use Ecto.Migration

  def change do
    create table(:iterations) do
      add :run_id, references(:runs, on_delete: :delete_all), null: false
      add :n, :integer, null: false
      add :prompt, :string
      add :agent_exit, :integer
      add :verify_exit, :integer
      add :log_ref, :string

      timestamps(type: :utc_datetime)
    end

    create index(:iterations, [:run_id])
  end
end
