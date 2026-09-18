defmodule FleetAdmin.Repo.Migrations.AddBuildReferenceToRuns do
  use Ecto.Migration

  def change do
    alter table(:runs) do
      add :build_url, :string
      add :build_number, :integer
    end
  end
end
