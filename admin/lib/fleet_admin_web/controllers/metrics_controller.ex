defmodule FleetAdminWeb.MetricsController do
  @moduledoc "Prometheus text-format metrics for the run ledger (P5)."

  use FleetAdminWeb, :controller

  alias FleetAdmin.Ledger

  def show(conn, _params) do
    counts = Ledger.status_counts()
    total = counts |> Map.values() |> Enum.sum()
    active = Map.get(counts, "running", 0)

    lines = [
      "# HELP fleet_runs_total Number of tracked runs by status.",
      "# TYPE fleet_runs_total gauge",
      Enum.map(counts, fn {status, count} ->
        ~s(fleet_runs_total{status="#{status}"} #{count})
      end),
      "# HELP fleet_runs_active Number of runs currently in progress.",
      "# TYPE fleet_runs_active gauge",
      "fleet_runs_active #{active}",
      "# HELP fleet_runs_tracked_total Total number of tracked runs.",
      "# TYPE fleet_runs_tracked_total gauge",
      "fleet_runs_tracked_total #{total}"
    ]

    conn
    |> put_resp_content_type("text/plain")
    |> send_resp(200, Enum.join(List.flatten(lines), "\n") <> "\n")
  end
end
