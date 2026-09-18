defmodule FleetAdmin.Ledger.AuditEvent do
  @moduledoc "A COI/OS audit event shipped to the panel (P5)."

  use Ecto.Schema
  import Ecto.Changeset

  schema "audit_events" do
    field :ts, :utc_datetime
    field :severity, :string
    field :action, :string
    field :detail, :string
    field :container, :string

    belongs_to :run, FleetAdmin.Ledger.Run

    timestamps(type: :utc_datetime)
  end

  def changeset(audit_event, attrs) do
    audit_event
    |> cast(attrs, [:run_id, :ts, :severity, :action, :detail, :container])
    |> foreign_key_constraint(:run_id)
  end
end
