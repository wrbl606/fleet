defmodule FleetAdminWeb.TriggerControllerTest do
  use FleetAdminWeb.ConnCase, async: false

  @token "test-ingest-token"

  defp authed(conn), do: put_req_header(conn, "authorization", "Bearer " <> @token)

  setup do
    Req.Test.set_req_test_to_shared()
    :ok
  end

  test "triggers a run through the panel", %{conn: conn} do
    Req.Test.stub(FleetAdmin.Trigger, fn conn ->
      Req.Test.json(conn, %{"message" => "Triggered jobs."})
    end)

    conn =
      conn
      |> authed()
      |> post(~p"/api/trigger", %{
        "source" => "github",
        "event" => "issue_comment",
        "payload" => %{"action" => "created"}
      })

    body = json_response(conn, 200)
    assert body["ok"] == true
    assert body["status"] == 200
  end

  test "rejects an unknown source", %{conn: conn} do
    conn =
      conn
      |> authed()
      |> post(~p"/api/trigger", %{"source" => "nope", "payload" => %{}})

    assert %{"ok" => false} = json_response(conn, 422)
  end

  test "requires a bearer token", %{conn: conn} do
    conn = post(conn, ~p"/api/trigger", %{"source" => "jira", "payload" => %{}})
    assert %{"error" => "unauthorized"} = json_response(conn, 401)
  end
end
