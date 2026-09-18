defmodule FleetAdminWeb.IngestController do
  @moduledoc "Run-ledger ingest API (plan §11.1)."

  use FleetAdminWeb, :controller

  alias FleetAdmin.Ledger

  def create(conn, params) do
    case Ledger.ingest_event(params) do
      {:ok, record} ->
        conn
        |> put_status(:created)
        |> json(%{ok: true, id: record.id})

      {:error, reason} ->
        conn
        |> put_status(:unprocessable_entity)
        |> json(%{ok: false, error: format_error(reason)})
    end
  end

  defp format_error({:unknown_event, other}), do: "unknown event: #{other}"
  defp format_error(:missing_event), do: "missing event"
  defp format_error(%Ecto.Changeset{} = changeset), do: inspect(changeset.errors)
  defp format_error(other), do: inspect(other)
end
