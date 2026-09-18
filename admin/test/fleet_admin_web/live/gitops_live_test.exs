defmodule FleetAdminWeb.GitOpsLiveTest do
  use FleetAdminWeb.ConnCase, async: false

  import Phoenix.LiveViewTest

  setup do
    Req.Test.set_req_test_to_shared()
    :ok
  end

  defp stub_success do
    Req.Test.stub(FleetAdmin.GitOps, fn conn ->
      case {conn.method, conn.request_path} do
        {"GET", "/repos/acme/x/git/ref/heads/main"} ->
          Req.Test.json(conn, %{"object" => %{"sha" => "basesha"}})

        {"GET", "/repos/acme/x/git/commits/basesha"} ->
          Req.Test.json(conn, %{"tree" => %{"sha" => "treesha"}})

        {"POST", "/repos/acme/x/git/blobs"} ->
          Req.Test.json(conn, %{"sha" => "blobsha"})

        {"POST", "/repos/acme/x/git/trees"} ->
          Req.Test.json(conn, %{"sha" => "newtree"})

        {"POST", "/repos/acme/x/git/commits"} ->
          Req.Test.json(conn, %{"sha" => "commitsha"})

        {"POST", "/repos/acme/x/git/refs"} ->
          Req.Test.json(conn, %{"ref" => "refs/heads/fleet/gitops-1"})

        {"POST", "/repos/acme/x/pulls"} ->
          Req.Test.json(conn, %{"number" => 5, "html_url" => "https://github.com/acme/x/pull/5"})
      end
    end)
  end

  test "renders the GitOps form", %{conn: conn} do
    {:ok, view, _html} = live(conn, ~p"/gitops")
    assert has_element?(view, "#gitops-form")
    refute has_element?(view, "#gitops-unconfigured")
  end

  test "opens a pull request on submit", %{conn: conn} do
    stub_success()

    {:ok, view, _html} = live(conn, ~p"/gitops")

    html =
      view
      |> form("#gitops-form",
        gitops: %{
          repo: "acme/x",
          base: "main",
          path: "registry.yaml",
          title: "fleet: update",
          content: "defaults:\n",
          body: "body"
        }
      )
      |> render_submit()

    assert html =~ "https://github.com/acme/x/pull/5"
    assert has_element?(view, "#gitops-result")
  end

  test "shows the unconfigured banner when no token is set", %{conn: conn} do
    previous = Application.get_env(:fleet_admin, :github_token)
    Application.put_env(:fleet_admin, :github_token, nil)
    on_exit(fn -> Application.put_env(:fleet_admin, :github_token, previous) end)

    {:ok, view, _html} = live(conn, ~p"/gitops")
    assert has_element?(view, "#gitops-unconfigured")
  end
end
