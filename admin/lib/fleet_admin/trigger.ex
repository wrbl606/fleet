defmodule FleetAdmin.Trigger do
  @moduledoc """
  Fire a webhook-like event at the configured dispatcher endpoint — normally
  the Jenkins Generic Webhook Trigger — to start a fleet run. Intended for
  testing the pipeline end-to-end without a real PM-tool webhook.

  The endpoint and token are trusted configuration (`FLEET_WEBHOOK_URL` /
  `FLEET_WEBHOOK_TOKEN`), never supplied by the caller. `source` is sent as a
  query parameter and the event name as the `x-fleet-event` header, matching
  the `Jenkinsfile` Generic Webhook Trigger wiring.
  """

  @sources ~w(jira linear github)

  def sources, do: @sources

  def configured? do
    url = Application.get_env(:fleet_admin, :fleet_webhook_url)
    is_binary(url) and url != ""
  end

  @doc "The endpoint that would be called for `source` (token included)."
  def endpoint(source \\ nil) do
    base = Application.get_env(:fleet_admin, :fleet_webhook_url) || ""

    %{}
    |> maybe_put("source", source)
    |> maybe_put("token", Application.get_env(:fleet_admin, :fleet_webhook_token))
    |> then(&merge_query(base, &1))
  end

  @doc """
  Send `payload` (a map or JSON string) for `source`/`event`.

  Options: `:dry_run` (preview only) and `:req_options` (e.g. `Req.Test`).
  Returns `{:ok, result}` or `{:error, reason}`.
  """
  def trigger(source, event, payload, opts \\ []) do
    with :ok <- validate_source(source),
         :ok <- validate_configured(),
         {:ok, body} <- decode_payload(payload) do
      body = maybe_inject_event(body, event)

      if Keyword.get(opts, :dry_run, false) do
        {:ok, %{dry_run: true, status: nil, url: endpoint(source), body: body}}
      else
        do_request(source, event, body, opts)
      end
    end
  end

  # -- request -------------------------------------------------------------

  defp do_request(source, event, body, opts) do
    req_options =
      Keyword.merge(
        Application.get_env(:fleet_admin, :fleet_webhook_req_options, []),
        Keyword.get(opts, :req_options, [])
      )

    params =
      %{}
      |> maybe_put("source", source)
      |> maybe_put("token", Application.get_env(:fleet_admin, :fleet_webhook_token))

    req =
      Req.new(
        method: :post,
        url: Application.get_env(:fleet_admin, :fleet_webhook_url),
        headers: headers(event),
        params: params,
        json: body,
        retry: false
      )
      |> Req.merge(req_options)

    case Req.request(req) do
      {:ok, %{status: status, body: response_body}} ->
        {:ok, %{status: status, body: response_body, url: endpoint(source)}}

      {:error, reason} ->
        {:error, reason}
    end
  end

  defp headers(event) do
    base = [{"accept", "application/json"}, {"user-agent", "fleet-admin"}]
    base = if is_binary(event) and event != "", do: [{"x-fleet-event", event} | base], else: base
    maybe_auth_header(base, Application.get_env(:fleet_admin, :fleet_webhook_token))
  end

  defp maybe_auth_header(headers, token) when is_binary(token) and token != "",
    do: [{"authorization", "Bearer " <> token} | headers]

  defp maybe_auth_header(headers, _), do: headers

  # -- payload -------------------------------------------------------------

  defp decode_payload(payload) when is_map(payload), do: {:ok, payload}

  defp decode_payload(payload) when is_binary(payload) do
    case Jason.decode(payload) do
      {:ok, map} when is_map(map) -> {:ok, map}
      {:ok, _other} -> {:error, :payload_must_be_object}
      {:error, _} -> {:error, :invalid_json}
    end
  end

  defp decode_payload(_), do: {:error, :invalid_payload}

  defp maybe_inject_event(%{"webhookEvent" => _} = body, _event), do: body

  defp maybe_inject_event(body, event) when is_binary(event) and event != "",
    do: Map.put(body, "webhookEvent", event)

  defp maybe_inject_event(body, _event), do: body

  # -- validation / helpers ------------------------------------------------

  defp validate_source(source) when source in @sources, do: :ok
  defp validate_source(source), do: {:error, {:unknown_source, source}}

  defp validate_configured do
    if configured?(), do: :ok, else: {:error, :not_configured}
  end

  defp maybe_put(map, _key, value) when value in [nil, ""], do: map
  defp maybe_put(map, key, value), do: Map.put(map, key, value)

  defp merge_query("", _params), do: ""
  defp merge_query(base, params) when params == %{}, do: base

  defp merge_query(base, params) do
    uri = URI.parse(base)
    existing = URI.decode_query(uri.query || "")
    %{uri | query: URI.encode_query(Map.merge(existing, params))} |> URI.to_string()
  end
end
