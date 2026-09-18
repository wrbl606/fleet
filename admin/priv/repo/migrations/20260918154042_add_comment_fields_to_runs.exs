defmodule FleetAdmin.Repo.Migrations.AddCommentFieldsToRuns do
  use Ecto.Migration

  def change do
    alter table(:runs) do
      add :mode, :string
      add :comment_url, :string
      add :comment_command, :string
      add :reply_url, :string
    end
  end
end
