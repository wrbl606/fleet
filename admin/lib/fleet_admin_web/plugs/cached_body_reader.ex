defmodule FleetAdminWeb.Plugs.CachedBodyReader do
  @moduledoc """
  `Plug.Parsers` body reader that preserves the raw request body.

  GitHub signs the exact bytes sent (`X-Hub-Signature-256`), so the body has to
  survive parsing. For `/api/*` requests the raw body is stashed in
  `conn.assigns[:raw_body]` for `FleetAdminWeb.Plugs.ApiAuth` to verify.
  """

  @doc false
  def read_body(conn, opts) do
    with {:ok, raw, conn} <- read_all(conn, opts, []) do
      if String.starts_with?(conn.request_path, "/api/") do
        {:ok, raw, Plug.Conn.assign(conn, :raw_body, raw)}
      else
        {:ok, raw, conn}
      end
    end
  end

  defp read_all(conn, opts, acc) do
    case Plug.Conn.read_body(conn, opts) do
      {:ok, body, conn} -> {:ok, IO.iodata_to_binary([acc, body]), conn}
      {:more, body, conn} -> read_all(conn, opts, [acc, body])
      {:error, reason} -> {:error, reason}
    end
  end
end
