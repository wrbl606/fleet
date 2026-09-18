defmodule FleetAdminWeb.MetricsControllerTest do
  use FleetAdminWeb.ConnCase, async: false

  alias FleetAdmin.Ledger

  @token "test-ingest-token"

  defp authed(conn), do: put_req_header(conn, "authorization", "Bearer " <> @token)

  test "exposes run counts in Prometheus format", %{conn: conn} do
    {:ok, _} =
      Ledger.ingest_event(%{
        "event" => "run.finished",
        "issue" => %{"source" => "jira", "key" => "ENG-M1"},
        "repo" => "acme/x",
        "branch" => "fleet/ENG-M1",
        "status" => "succeeded"
      })

    {:ok, _} =
      Ledger.ingest_event(%{
        "event" => "run.started",
        "issue" => %{"source" => "jira", "key" => "ENG-M2"},
        "repo" => "acme/x",
        "branch" => "fleet/ENG-M2"
      })

    conn = conn |> authed() |> get(~p"/api/metrics")
    body = response(conn, 200)

    assert body =~ ~s(fleet_runs_total{status="succeeded"} 1)
    assert body =~ ~s(fleet_runs_total{status="running"} 1)
    assert body =~ "fleet_runs_active 1"
    assert body =~ "fleet_runs_tracked_total 2"
  end

  test "requires the bearer token", %{conn: conn} do
    conn = get(conn, ~p"/api/metrics")
    assert response(conn, 401)
  end
end
