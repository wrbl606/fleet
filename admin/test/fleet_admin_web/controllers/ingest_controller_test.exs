defmodule FleetAdminWeb.IngestControllerTest do
  use FleetAdminWeb.ConnCase, async: false

  @token "test-ingest-token"

  defp authed(conn), do: put_req_header(conn, "authorization", "Bearer " <> @token)

  setup do
    Req.Test.set_req_test_to_shared()
    :ok
  end

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

  test "accepts a raw webhook, records it and forwards it to the dispatcher", %{conn: conn} do
    Req.Test.stub(FleetAdmin.Trigger, fn conn ->
      Req.Test.json(conn, %{"message" => "Triggered jobs."})
    end)

    payload = %{"webhookEvent" => "jira:issue_created", "issue" => %{"key" => "ENG-1"}}

    conn =
      conn
      |> authed()
      |> put_req_header("x-fleet-event", "jira:issue_created")
      |> post(~p"/api/ingest?source=jira", payload)

    assert %{"ok" => true, "id" => id, "forward" => %{"status" => 200}} =
             json_response(conn, 201)

    assert FleetAdmin.Ledger.get_ingest_event!(id).event == "webhook.received"
  end

  test "accepts a GitHub webhook authenticated by HMAC signature", %{conn: conn} do
    secret = "test-gh-webhook-secret"
    previous = Application.get_env(:fleet_admin, :github_webhook_secret)
    Application.put_env(:fleet_admin, :github_webhook_secret, secret)
    on_exit(fn -> Application.put_env(:fleet_admin, :github_webhook_secret, previous) end)

    Req.Test.stub(FleetAdmin.Trigger, fn conn -> Req.Test.json(conn, %{"ok" => true}) end)

    body = ~s({"action":"created","issue":{"number":14}})

    signature =
      "sha256=" <> Base.encode16(:crypto.mac(:hmac, :sha256, secret, body), case: :lower)

    conn =
      conn
      |> put_req_header("content-type", "application/json")
      |> put_req_header("x-hub-signature-256", signature)
      |> put_req_header("x-github-event", "issue_comment")
      |> post(~p"/api/ingest?source=github", body)

    assert %{"ok" => true, "id" => _id, "forward" => %{"status" => 200}} =
             json_response(conn, 201)
  end

  test "rejects a bad GitHub signature", %{conn: conn} do
    previous = Application.get_env(:fleet_admin, :github_webhook_secret)
    Application.put_env(:fleet_admin, :github_webhook_secret, "test-gh-webhook-secret")
    on_exit(fn -> Application.put_env(:fleet_admin, :github_webhook_secret, previous) end)

    Req.Test.stub(FleetAdmin.Trigger, fn conn -> Req.Test.json(conn, %{"ok" => true}) end)

    conn =
      conn
      |> put_req_header("content-type", "application/json")
      |> put_req_header("x-hub-signature-256", "sha256=deadbeef")
      |> post(~p"/api/ingest?source=github", ~s({"action":"created"}))

    assert json_response(conn, 401)
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
