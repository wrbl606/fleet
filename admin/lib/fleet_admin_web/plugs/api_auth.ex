defmodule FleetAdminWeb.Plugs.ApiAuth do
  @moduledoc """
  Auth for the ingest API (`/api/*`).

  A request is allowed when either:

    * it carries `Authorization: Bearer <FLEET_INGEST_TOKEN>` (dispatcher
      lifecycle events, scripts, the panel's own calls); or
    * it carries a valid GitHub `X-Hub-Signature-256` HMAC over the raw body and
      `:github_webhook_secret` is configured. GitHub webhooks cannot set custom
      headers, so the HMAC is the only usable control for them.

  Tokens are compared in constant time. When neither `:ingest_token` nor
  `:github_webhook_secret` is configured the API is open — dev only.
  """

  @behaviour Plug

  import Plug.Conn

  @impl true
  def init(opts), do: opts

  @impl true
  def call(conn, _opts) do
    token = Application.get_env(:fleet_admin, :ingest_token)
    secret = Application.get_env(:fleet_admin, :github_webhook_secret)

    cond do
      valid_bearer?(conn, token) -> conn
      valid_github_signature?(conn, secret) -> conn
      configured?(token) or configured?(secret) -> unauthorized(conn)
      true -> conn
    end
  end

  defp configured?(value), do: is_binary(value) and value != ""

  defp valid_bearer?(conn, expected) when is_binary(expected) and expected != "" do
    case get_req_header(conn, "authorization") do
      ["Bearer " <> got] ->
        byte_size(got) == byte_size(expected) and Plug.Crypto.secure_compare(got, expected)

      _ ->
        false
    end
  end

  defp valid_bearer?(_conn, _expected), do: false

  defp valid_github_signature?(conn, secret) when is_binary(secret) and secret != "" do
    case get_req_header(conn, "x-hub-signature-256") do
      [signature] ->
        raw = Map.get(conn.assigns, :raw_body, "")

        expected =
          "sha256=" <> Base.encode16(:crypto.mac(:hmac, :sha256, secret, raw), case: :lower)

        byte_size(signature) == byte_size(expected) and
          Plug.Crypto.secure_compare(signature, expected)

      _ ->
        false
    end
  end

  defp valid_github_signature?(_conn, _secret), do: false

  defp unauthorized(conn) do
    conn
    |> put_resp_content_type("application/json")
    |> send_resp(401, Jason.encode!(%{ok: false, error: "unauthorized"}))
    |> halt()
  end
end
