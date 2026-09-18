defmodule FleetAdmin.Repo.Migrations.CreatePrs do
  use Ecto.Migration

  def change do
    create table(:prs) do
      add :run_id, references(:runs, on_delete: :delete_all), null: false
      add :url, :string
      add :number, :integer
      add :state, :string, null: false, default: "open"

      timestamps(type: :utc_datetime)
    end

    create index(:prs, [:run_id])
  end
end
