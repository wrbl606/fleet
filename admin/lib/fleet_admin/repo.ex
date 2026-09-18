defmodule FleetAdmin.Repo do
  use Ecto.Repo,
    otp_app: :fleet_admin,
    adapter: Ecto.Adapters.SQLite3
end
