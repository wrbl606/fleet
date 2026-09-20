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

  test "persists PR-comment fields", %{conn: conn} do
    payload = %{
      "event" => "run.finished",
      "issue" => %{"source" => "github", "key" => "o/r#14"},
      "repo" => "o/r",
      "branch" => "feature/x",
      "status" => "succeeded",
      "mode" => "auto",
      "comment_url" => "https://github.com/o/r/pull/14#issuecomment-1",
      "comment_command" => "/agent fix it",
      "reply_url" => "https://github.com/o/r/pull/14#issuecomment-2"
    }

    conn = conn |> authed() |> post(~p"/api/ingest", payload)
    assert %{"ok" => true, "id" => id} = json_response(conn, 201)

    run = FleetAdmin.Ledger.get_run!(id)
    assert run.mode == "auto"
    assert run.comment_command == "/agent fix it"
    assert run.reply_url =~ "issuecomment-2"
  end

  test "ingests a webhook.received debug event", %{conn: conn} do
    payload = %{
      "event" => "webhook.received",
      "source" => "github",
      "webhook_event" => "issue_comment",
      "delivery" => "d-1",
      "payload" => ~s({"action":"created"})
    }

    conn = conn |> authed() |> post(~p"/api/ingest", payload)
    assert %{"ok" => true, "id" => id} = json_response(conn, 201)
    assert FleetAdmin.Ledger.get_ingest_event!(id).event == "webhook.received"
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
