defmodule FleetAdminWeb.RunLiveTest do
  use FleetAdminWeb.ConnCase, async: false

  import Phoenix.LiveViewTest

  alias FleetAdmin.Ledger

  defp ingest(attrs \\ %{}) do
    payload =
      Map.merge(
        %{
          "event" => "run.finished",
          "issue" => %{"source" => "jira", "key" => "ENG-1"},
          "repo" => "acme/engine-api",
          "branch" => "fleet/ENG-1",
          "status" => "succeeded",
          "tool" => "claude",
          "build_url" => "https://jenkins.example/job/fleet-dispatcher/1/",
          "build_number" => 1,
          "iterations" => [
            %{"n" => 1, "agent" => %{"exit_code" => 0}, "verify" => %{"exit_code" => 0}}
          ]
        },
        attrs
      )

    {:ok, run} = Ledger.ingest_event(payload)
    run
  end

  test "index lists runs", %{conn: conn} do
    run = ingest()
    {:ok, view, html} = live(conn, ~p"/")

    assert html =~ "Fleet runs"
    assert has_element?(view, "#runs")
    assert render(view) =~ run.issue_key
    assert has_element?(view, "#build-#{run.id}")
  end

  test "nav links to the Jenkins master when configured", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/")
    assert has_element?(view, "#jenkins-link")
  end

  test "index shows an empty state", %{conn: conn} do
    {:ok, _view, html} = live(conn, ~p"/")
    assert html =~ "No runs yet"
  end

  test "index updates live when a run is ingested", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/")
    run = ingest(%{"issue" => %{"source" => "jira", "key" => "ENG-LIVE"}})

    assert render(view) =~ "ENG-LIVE"
    assert render(view) =~ run.repo
  end

  test "index filters by status", %{conn: conn} do
    ingest(%{"status" => "failed", "issue" => %{"source" => "jira", "key" => "ENG-FAIL"}})
    ingest(%{"status" => "succeeded", "issue" => %{"source" => "jira", "key" => "ENG-OK"}})

    {:ok, view, html} = live(conn, ~p"/")
    assert html =~ "ENG-FAIL"
    assert html =~ "ENG-OK"

    filtered = render_change(view, "filter", %{"filter" => %{"status" => "failed"}})
    assert filtered =~ "ENG-FAIL"
    refute filtered =~ "ENG-OK"
  end

  test "show renders run detail with iterations", %{conn: conn} do
    run = ingest()
    {:ok, view, html} = live(conn, ~p"/runs/#{run.id}")

    assert html =~ run.issue_key
    assert has_element?(view, "#iterations")
    assert has_element?(view, "#run-build")
    assert has_element?(view, "#run-error") == false
  end

  test "show renders the error banner for failed runs", %{conn: conn} do
    run = ingest(%{"status" => "failed", "error" => "verify.sh still failing"})
    {:ok, view, _html} = live(conn, ~p"/runs/#{run.id}")

    assert has_element?(view, "#run-error")
    assert render(view) =~ "verify.sh still failing"
  end
end
