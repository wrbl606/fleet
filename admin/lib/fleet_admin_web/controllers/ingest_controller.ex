defmodule FleetAdminWeb.IngestController do
  @moduledoc """
  Run-ledger ingest API (plan §11.1) and the public webhook entry point.

  * With a `source` query parameter (or `x-fleet-source` header) the request is
    treated as an inbound PM-tool webhook: it is recorded as `webhook.received`
    and forwarded to the dispatcher (Jenkins GWT). See `FleetAdmin.Ingest`.
  * Otherwise the body is a dispatcher lifecycle event recorded in the ledger.
  """

  use FleetAdminWeb, :controller

  alias FleetAdmin.{Ingest, Ledger}

  @github_headers ~w(x-github-event x-github-delivery)

  def create(conn, params) do
    case ingest_source(conn) do
      source when is_binary(source) and source != "" ->
        ingest_webhook(conn, source, params)

      _ ->
        ingest_ledger(conn, params)
    end
  end

  defp ingest_source(conn) do
    conn.query_params["source"] || List.first(get_req_header(conn, "x-fleet-source"))
  end

  defp ingest_ledger(conn, params) do
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

  defp ingest_webhook(conn, source, params) do
    event = conn.query_params["event"] || List.first(get_req_header(conn, "x-fleet-event"))
    opts = [extra_headers: passthrough_headers(conn)]

    case Ingest.accept_webhook(source, event, params, opts) do
      {:ok, %{record: record, forward: forward}} ->
        conn
        |> put_status(:created)
        |> json(%{ok: true, id: record.id, forward: forward_summary(forward)})

      {:error, reason} ->
        conn
        |> put_status(:unprocessable_entity)
        |> json(%{ok: false, error: format_error(reason)})
    end
  end

  defp passthrough_headers(conn) do
    for name <- @github_headers,
        value = List.first(get_req_header(conn, name)),
        is_binary(value),
        do: {name, value}
  end

  defp forward_summary({:ok, %{dry_run: true}}), do: %{dry_run: true}
  defp forward_summary({:ok, %{status: status}}), do: %{status: status}
  defp forward_summary({:error, reason}), do: %{error: format_error(reason)}

  defp format_error({:unknown_event, other}), do: "unknown event: #{other}"
  defp format_error(:missing_event), do: "missing event"
  defp format_error(:invalid_json), do: "invalid_json"
  defp format_error(:payload_must_be_object), do: "payload_must_be_object"
  defp format_error(:invalid_payload), do: "invalid_payload"
  defp format_error(:not_configured), do: "webhook endpoint not configured"
  defp format_error(%Ecto.Changeset{} = changeset), do: inspect(changeset.errors)
  defp format_error(other), do: inspect(other)
end
