defmodule FleetAdmin.Ledger.Pr do
  @moduledoc "A GitHub pull request opened for a run."

  use Ecto.Schema
  import Ecto.Changeset

  schema "prs" do
    field :url, :string
    field :number, :integer
    field :state, :string, default: "open"

    belongs_to :run, FleetAdmin.Ledger.Run

    timestamps(type: :utc_datetime)
  end

  def changeset(pr, attrs) do
    pr
    |> cast(attrs, [:run_id, :url, :number, :state])
    |> foreign_key_constraint(:run_id)
  end
end
