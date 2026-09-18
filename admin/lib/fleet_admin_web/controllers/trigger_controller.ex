defmodule FleetAdminWeb.TriggerController do
  @moduledoc """
  Programmatic trigger API — the same path the Trigger page uses.

  POST /api/trigger with `{"source","event","payload"}` (bearer-authenticated
  with `FLEET_INGEST_TOKEN`). Useful for scripts and end-to-end tests so a run
  is initiated *through* the admin panel rather than by calling Jenkins
  directly.
  """

  use FleetAdminWeb, :controller

  alias FleetAdmin.Trigger

  def create(conn, params) do
    source = params["source"] || "jira"
    event = params["event"]
    dry_run = params["dry_run"] in [true, "true", "on", 1]
    payload = params["payload"] || Map.drop(params, ["source", "event", "dry_run"])

    case Trigger.trigger(source, event, payload, dry_run: dry_run) do
      {:ok, result} ->
        conn
        |> put_status(:ok)
        |> json(Map.put(result, :ok, true))

      {:error, reason} ->
        conn
        |> put_status(:unprocessable_entity)
        |> json(%{ok: false, error: format_error(reason)})
    end
  end

  defp format_error(:not_configured), do: "webhook endpoint not configured"
  defp format_error(:invalid_json), do: "invalid_json"
  defp format_error(:payload_must_be_object), do: "payload_must_be_object"
  defp format_error({:unknown_source, source}), do: "unknown_source: #{source}"
  defp format_error(other), do: inspect(other)
end
