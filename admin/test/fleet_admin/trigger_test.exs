defmodule FleetAdmin.TriggerTest do
  use ExUnit.Case, async: false

  alias FleetAdmin.Trigger

  @payload ~s({"issue":{"key":"ENG-1"}})

  test "configured?/0 reflects the endpoint" do
    assert Trigger.configured?()
  end

  test "sends a webhook-like POST with source, token and event header" do
    parent = self()

    Req.Test.stub(FleetAdmin.Trigger, fn conn ->
      send(parent, {:req, conn})
      Req.Test.json(conn, %{"ok" => true})
    end)

    assert {:ok, %{status: 200}} =
             Trigger.trigger("jira", "jira:issue_created", @payload)

    assert_received {:req, conn}
    assert conn.method == "POST"
    assert conn.request_path == "/generic-webhook-trigger/invoke"
    assert conn.query_params["source"] == "jira"
    assert conn.query_params["token"] == "test-webhook-token"
    assert {"x-fleet-event", "jira:issue_created"} in conn.req_headers

    body = Jason.decode!(Req.Test.raw_body(conn))
    assert body["webhookEvent"] == "jira:issue_created"
    assert body["issue"]["key"] == "ENG-1"
  end

  test "dry run returns a preview without calling the endpoint" do
    assert {:ok, preview} =
             Trigger.trigger("jira", "jira:issue_created", @payload, dry_run: true)

    assert preview.dry_run
    assert preview.url =~ "generic-webhook-trigger"
    assert preview.body["webhookEvent"] == "jira:issue_created"
  end

  test "rejects invalid JSON" do
    assert {:error, :invalid_json} = Trigger.trigger("jira", "x", "{not json")
  end

  test "rejects non-object JSON" do
    assert {:error, :payload_must_be_object} = Trigger.trigger("jira", "x", "[1,2,3]")
  end

  test "rejects an unknown source" do
    assert {:error, {:unknown_source, "bogus"}} = Trigger.trigger("bogus", "x", @payload)
  end

  test "errors when no endpoint is configured" do
    previous = Application.get_env(:fleet_admin, :fleet_webhook_url)
    Application.put_env(:fleet_admin, :fleet_webhook_url, nil)
    on_exit(fn -> Application.put_env(:fleet_admin, :fleet_webhook_url, previous) end)

    assert {:error, :not_configured} = Trigger.trigger("jira", "x", @payload)
  end
end
