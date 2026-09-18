defmodule FleetAdmin.GitOpsTest do
  use ExUnit.Case, async: false

  alias FleetAdmin.GitOps

  test "configured?/0 reflects the token" do
    assert GitOps.configured?()
  end

  test "open_pr walks the git data API and returns the PR" do
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
          Req.Test.json(conn, %{"number" => 42, "html_url" => "https://github.com/acme/x/pull/42"})
      end
    end)

    files = [%{"path" => "registry.yaml", "content" => "defaults:\n"}]

    assert {:ok, result} =
             GitOps.open_pr("acme/x", "main", files, "fleet: update", "body",
               branch: "fleet/gitops-1"
             )

    assert result.pr_url == "https://github.com/acme/x/pull/42"
    assert result.number == 42
    assert result.branch == "fleet/gitops-1"
    assert result.commit == "commitsha"
  end

  test "falls back to PATCH when the branch already exists" do
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
          Plug.Conn.send_resp(conn, 422, ~s({"message":"Reference already exists"}))

        {"PATCH", "/repos/acme/x/git/refs/heads/fleet/gitops-1"} ->
          Req.Test.json(conn, %{"ref" => "refs/heads/fleet/gitops-1"})

        {"POST", "/repos/acme/x/pulls"} ->
          Req.Test.json(conn, %{"number" => 1, "html_url" => "https://github.com/acme/x/pull/1"})
      end
    end)

    files = [%{"path" => "a.txt", "content" => "hi"}]

    assert {:ok, result} =
             GitOps.open_pr("acme/x", "main", files, "t", "b", branch: "fleet/gitops-1")

    assert result.pr_url == "https://github.com/acme/x/pull/1"
  end

  test "requires at least one file" do
    assert {:error, :no_files} = GitOps.open_pr("acme/x", "main", [], "t", "b")
  end

  test "propagates GitHub errors" do
    Req.Test.stub(FleetAdmin.GitOps, fn conn ->
      Plug.Conn.send_resp(conn, 404, ~s({"message":"Not Found"}))
    end)

    assert {:error, {404, _}} =
             GitOps.open_pr(
               "acme/missing",
               "main",
               [%{"path" => "a", "content" => "b"}],
               "t",
               "b"
             )
  end
end
