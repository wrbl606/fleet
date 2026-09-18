defmodule FleetAdminWeb.TriggerLiveTest do
  use FleetAdminWeb.ConnCase, async: false

  import Phoenix.LiveViewTest

  @payload ~s({"issue":{"key":"ENG-1"}})

  setup do
    Req.Test.set_req_test_to_shared()
    :ok
  end

  test "renders the trigger form and endpoint", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/trigger")

    assert has_element?(view, "#trigger-form")
    assert has_element?(view, "#trigger-endpoint")
    refute has_element?(view, "#trigger-unconfigured")
  end

  test "dry run previews the request", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/trigger")

    html =
      view
      |> form("#trigger-form",
        trigger: %{
          "source" => "jira",
          "event" => "jira:issue_created",
          "payload" => @payload,
          "dry_run" => "true"
        }
      )
      |> render_submit()

    assert has_element?(view, "#trigger-result")
    assert html =~ "Dry run preview"
  end

  test "sends the webhook-like request", %{conn: conn} do
    Req.Test.stub(FleetAdmin.Trigger, fn conn -> Req.Test.json(conn, %{"ok" => true}) end)

    {:ok, view, _html} = live(conn, ~p"/trigger")

    html =
      view
      |> form("#trigger-form",
        trigger: %{
          "source" => "jira",
          "event" => "jira:issue_created",
          "payload" => @payload
        }
      )
      |> render_submit()

    assert html =~ "HTTP 200"
  end

  test "shows an error for invalid JSON", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/trigger")

    view
    |> form("#trigger-form",
      trigger: %{"source" => "jira", "event" => "x", "payload" => "{oops"}
    )
    |> render_submit()

    assert has_element?(view, "#trigger-json-error")
  end

  test "shows the Jenkins master link when configured", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/trigger")
    assert has_element?(view, "#jenkins-master")
  end

  test "hides the Jenkins master link when unset", %{conn: conn} do
    previous = Application.get_env(:fleet_admin, :fleet_jenkins_url)
    Application.put_env(:fleet_admin, :fleet_jenkins_url, nil)
    on_exit(fn -> Application.put_env(:fleet_admin, :fleet_jenkins_url, previous) end)

    {:ok, view, _html} = live(conn, ~p"/trigger")
    refute has_element?(view, "#jenkins-master")
  end

  test "loads the GitHub PR comment preset", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/trigger")

    html = view |> element("#preset-github-comment") |> render_click()

    assert html =~ "issue_comment"
    assert html =~ "/agent"
    assert html =~ "github"
  end

  test "shows the unconfigured banner when no endpoint is set", %{conn: conn} do
    previous = Application.get_env(:fleet_admin, :fleet_webhook_url)
    Application.put_env(:fleet_admin, :fleet_webhook_url, nil)
    on_exit(fn -> Application.put_env(:fleet_admin, :fleet_webhook_url, previous) end)

    {:ok, view, _html} = live(conn, ~p"/trigger")
    assert has_element?(view, "#trigger-unconfigured")
  end
end
