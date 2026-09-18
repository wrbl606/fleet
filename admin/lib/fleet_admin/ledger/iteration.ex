defmodule FleetAdmin.Ledger.Iteration do
  @moduledoc "One setup/agent/verify iteration within a run."

  use Ecto.Schema
  import Ecto.Changeset

  schema "iterations" do
    field :n, :integer
    field :prompt, :string
    field :agent_exit, :integer
    field :verify_exit, :integer
    field :log_ref, :string

    belongs_to :run, FleetAdmin.Ledger.Run

    timestamps(type: :utc_datetime)
  end

  def changeset(iteration, attrs) do
    iteration
    |> cast(attrs, [:run_id, :n, :prompt, :agent_exit, :verify_exit, :log_ref])
    |> validate_required([:n])
    |> foreign_key_constraint(:run_id)
  end
end
