defmodule FleetAdminWeb.Plugs.ApiAuth do
  @moduledoc """
  Bearer-token auth for the ingest API (`/api/*`).

  Enabled when `config :fleet_admin, :ingest_token` is set (from
  `FLEET_INGEST_TOKEN`). Compared in constant time.
  """

  @behaviour Plug

  import Plug.Conn

  @impl true
  def init(opts), do: opts

  @impl true
  def call(conn, _opts) do
    expected = Application.get_env(:fleet_admin, :ingest_token)

    cond do
      not is_binary(expected) or expected == "" ->
        conn

      valid_bearer?(conn, expected) ->
        conn

      true ->
        conn
        |> put_resp_content_type("application/json")
        |> send_resp(401, Jason.encode!(%{ok: false, error: "unauthorized"}))
        |> halt()
    end
  end

  defp valid_bearer?(conn, expected) do
    case get_req_header(conn, "authorization") do
      ["Bearer " <> got] ->
        byte_size(got) == byte_size(expected) and Plug.Crypto.secure_compare(got, expected)

      _ ->
        false
    end
  end
end
