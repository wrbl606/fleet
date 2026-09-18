defmodule FleetAdminWeb.IngestControllerTest do
  use FleetAdminWeb.ConnCase, async: false

  @token "test-ingest-token"

  defp authed(conn), do: put_req_header(conn, "authorization", "Bearer " <> @token)

  test "ingests a finished run", %{conn: conn} do
    payload = %{
      "event" => "run.finished",
      "issue" => %{"source" => "jira", "key" => "ENG-9"},
      "repo" => "acme/engine",
      "branch" => "fleet/ENG-9",
      "status" => "succeeded",
      "tool" => "opencode"
    }

    conn = conn |> authed() |> post(~p"/api/ingest", payload)
    assert %{"ok" => true, "id" => _id} = json_response(conn, 201)
  end

  test "rejects unknown events", %{conn: conn} do
    conn = conn |> authed() |> post(~p"/api/ingest", %{"event" => "nope"})
    assert %{"ok" => false} = json_response(conn, 422)
  end

  test "requires a bearer token", %{conn: conn} do
    conn = post(conn, ~p"/api/ingest", %{"event" => "nope"})
    assert %{"error" => "unauthorized"} = json_response(conn, 401)
  end
end
