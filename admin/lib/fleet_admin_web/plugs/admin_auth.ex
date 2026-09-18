defmodule FleetAdminWeb.Plugs.AdminAuth do
  @moduledoc """
  Optional HTTP Basic auth for the admin UI.

  Enabled only when `config :fleet_admin, :admin_basic_auth, {user, pass}` is
  set (from `FLEET_ADMIN_USER` / `FLEET_ADMIN_PASSWORD` at runtime). This is
  the offline baseline; replace with `phx.gen.auth` + Ueberauth GitHub OAuth
  (plan §11) when the team wants per-user accounts.
  """

  @behaviour Plug

  @impl true
  def init(opts), do: opts

  @impl true
  def call(conn, _opts) do
    case Application.get_env(:fleet_admin, :admin_basic_auth) do
      {user, pass} when is_binary(user) and is_binary(pass) and pass != "" ->
        Plug.BasicAuth.basic_auth(conn, username: user, password: pass)

      _ ->
        conn
    end
  end
end
