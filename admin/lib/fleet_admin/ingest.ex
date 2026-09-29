defmodule FleetAdmin.Ingest do
  @moduledoc """
  Inbound webhook entry point.

  `POST /api/ingest?source=<source>` accepts a raw PM-tool webhook (Jira, Linear,
  GitHub, ...), records it in the ledger as `webhook.received`, and forwards the
  payload verbatim to the configured dispatcher (Jenkins Generic Webhook Trigger)
  via `FleetAdmin.Trigger.forward/4`.

  Without a `source` query parameter (or `x-fleet-source` header) the endpoint
  keeps its original role: a ledger sink for the dispatcher's own lifecycle
  events (`run.started`, `run.finished`, ...), which are never forwarded.
  """

  alias FleetAdmin.{Ledger, Trigger}

  @doc """
  Record an inbound webhook and forward it to the dispatcher.

  Returns `{:ok, %{record: record, forward: forward_result}}`, or
  `{:ok, %{dry_run: true, endpoint: url, body: body}}` when `:dry_run` is set.
  """
  def accept_webhook(source, event, payload, opts \\ []) do
    with {:ok, body} <- normalize(payload) do
      if Keyword.get(opts, :dry_run, false) do
        {:ok, %{dry_run: true, endpoint: endpoint(source), body: body}}
      else
        with {:ok, record} <- record(source, event, body) do
          forward = Trigger.forward(source, event, body, opts)
          {:ok, %{record: record, forward: forward}}
        end
      end
    end
  end

  @doc """
  Public URL external senders should POST webhooks to (includes the `source`
  query parameter). Uses `:fleet_ingest_public_url` when configured, otherwise
  the panel's own endpoint URL.
  """
  def endpoint(source \\ nil) do
    base =
      Application.get_env(:fleet_admin, :fleet_ingest_public_url) ||
        FleetAdminWeb.Endpoint.url() <> "/api/ingest"

    case source do
      s when is_binary(s) and s != "" ->
        separator = if String.contains?(base, "?"), do: "&", else: "?"
        base <> separator <> "source=" <> URI.encode_www_form(s)

      _ ->
        base
    end
  end

  defp record(source, event, body) do
    Ledger.ingest_event(%{
      "event" => "webhook.received",
      "source" => source,
      "webhook_event" => event,
      "payload" => Jason.encode!(body)
    })
  end

  defp normalize(body) when is_map(body), do: {:ok, body}

  defp normalize(body) when is_binary(body) do
    case Jason.decode(body) do
      {:ok, map} when is_map(map) -> {:ok, map}
      {:ok, _other} -> {:error, :payload_must_be_object}
      {:error, _} -> {:error, :invalid_json}
    end
  end

  defp normalize(_body), do: {:error, :invalid_payload}
end
