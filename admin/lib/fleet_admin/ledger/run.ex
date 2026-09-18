defmodule FleetAdmin.Ledger.Run do
  @moduledoc "A single fleet agent run (one issue -> one PR)."

  use Ecto.Schema
  import Ecto.Changeset

  @statuses ~w(running succeeded no_changes verify_failed failed)

  schema "runs" do
    field :external_id, :string
    field :source, :string
    field :issue_key, :string
    field :repo, :string
    field :branch, :string
    field :commit, :string
    field :pr_url, :string
    field :status, :string, default: "running"
    field :tool, :string
    field :platform, :string
    field :cost, :float
    field :error, :string
    field :build_url, :string
    field :build_number, :integer
    field :started_at, :utc_datetime
    field :finished_at, :utc_datetime

    has_many :iterations, FleetAdmin.Ledger.Iteration
    has_many :prs, FleetAdmin.Ledger.Pr
    has_many :audit_events, FleetAdmin.Ledger.AuditEvent

    timestamps(type: :utc_datetime)
  end

  def statuses, do: @statuses

  def changeset(run, attrs) do
    run
    |> cast(attrs, [
      :external_id,
      :source,
      :issue_key,
      :repo,
      :branch,
      :commit,
      :pr_url,
      :status,
      :tool,
      :platform,
      :cost,
      :error,
      :build_url,
      :build_number,
      :started_at,
      :finished_at
    ])
    |> validate_required([:external_id, :status])
    |> validate_inclusion(:status, @statuses)
    |> unique_constraint(:external_id)
  end
end
