defmodule FleetAdminWeb.IngestLiveTest do
  use FleetAdminWeb.ConnCase, async: false

  import Phoenix.LiveViewTest

  alias FleetAdmin.Ledger

  test "renders the ingest log with routing outcomes", %{conn: conn} do
    {:ok, _} =
      Ledger.ingest_event(%{
        "event" => "resolve.result",
        "source" => "jira",
        "issue_key" => "ENG-1",
        "project" => "ENG",
        "resolution" => %{"repo" => "acme/engine"}
      })

    {:ok, _view, html} = live(conn, ~p"/ingest")

    assert html =~ "Ingest log"
    assert html =~ "acme/engine"
    assert html =~ "ENG-1"
  end

  test "shows the empty state", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/ingest")
    assert has_element?(view, "#ingest-empty")
  end
end
