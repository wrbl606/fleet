defmodule FleetAdmin.Ledger.IngestEvent do
  @moduledoc "A webhook/normalization/resolution event, for debugging ingest."

  use Ecto.Schema
  import Ecto.Changeset

  @statuses ~w(received ok filtered error)

  schema "ingest_events" do
    field :event, :string
    field :status, :string
    field :source, :string
    field :webhook_event, :string
    field :delivery, :string
    field :actionable, :boolean
    field :issue_key, :string
    field :project, :string
    field :repo, :string
    field :reason, :string
    field :detail, :string
    field :payload, :string

    timestamps(type: :utc_datetime)
  end

  def statuses, do: @statuses

  def changeset(event, attrs) do
    event
    |> cast(attrs, [
      :event,
      :status,
      :source,
      :webhook_event,
      :delivery,
      :actionable,
      :issue_key,
      :project,
      :repo,
      :reason,
      :detail,
      :payload
    ])
    |> validate_required([:event])
    |> validate_inclusion(:status, @statuses)
  end
end
