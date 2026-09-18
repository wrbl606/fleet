defmodule FleetAdmin.GitOps do
  @moduledoc """
  GitOps config writes (plan §11): commit file changes to a branch and open a
  pull request against `fleet-config` / a source repo using the GitHub REST
  API via `Req`.

  Returns `{:ok, %{pr_url: ..., branch: ..., commit: ...}}` or
  `{:error, reason}`. All network access goes through `Req`; tests stub it
  with `Req.Test`.
  """

  @github_accept "application/vnd.github+json"
  @github_version "2022-11-28"

  def configured? do
    token = Application.get_env(:fleet_admin, :github_token)
    is_binary(token) and token != ""
  end

  @doc """
  Commit `files` (list of `%{"path" =>, "content" =>}`) on a new branch and
  open a PR.

  Options: `:branch`, `:req_options`, `:message`, `:draft`.
  """
  def open_pr(repo, base, files, title, body, opts \\ [])

  def open_pr(_repo, _base, [], _title, _body, _opts), do: {:error, :no_files}

  def open_pr(repo, base, files, title, body, opts) do
    branch = Keyword.get(opts, :branch) || "fleet/gitops-#{System.system_time(:second)}"
    message = Keyword.get(opts, :message) || title
    req_options = Keyword.get(opts, :req_options, [])

    with {:ok, base_sha} <- base_ref_sha(repo, base, req_options),
         {:ok, tree_sha} <- base_tree_sha(repo, base_sha, req_options),
         {:ok, blobs} <- upload_blobs(repo, files, req_options),
         {:ok, new_tree} <- create_tree(repo, tree_sha, blobs, req_options),
         {:ok, commit_sha} <- create_commit(repo, message, new_tree, base_sha, req_options),
         :ok <- create_branch(repo, branch, commit_sha, req_options),
         {:ok, pr} <- create_pull_request(repo, branch, base, title, body, opts, req_options) do
      {:ok, %{pr_url: pr["html_url"], branch: branch, commit: commit_sha, number: pr["number"]}}
    end
  end

  # -- GitHub steps --------------------------------------------------------

  defp base_ref_sha(repo, base, req_options) do
    get_json("/repos/#{repo}/git/ref/heads/#{base}", req_options, &get_in(&1, ["object", "sha"]))
  end

  defp base_tree_sha(repo, base_sha, req_options) do
    get_json("/repos/#{repo}/git/commits/#{base_sha}", req_options, &get_in(&1, ["tree", "sha"]))
  end

  defp upload_blobs(repo, files, req_options) do
    Enum.reduce_while(files, {:ok, []}, fn file, {:ok, acc} ->
      body = %{content: file["content"], encoding: "utf-8"}

      case request(:post, "/repos/#{repo}/git/blobs", body, req_options) do
        {:ok, %{"sha" => sha}} -> {:cont, {:ok, [blob_entry(file, sha) | acc]}}
        {:ok, other} -> {:halt, {:error, {:blob_failed, other}}}
        {:error, reason} -> {:halt, {:error, reason}}
      end
    end)
    |> case do
      {:ok, blobs} -> {:ok, Enum.reverse(blobs)}
      error -> error
    end
  end

  defp blob_entry(file, sha) do
    %{path: file["path"], mode: "100644", type: "blob", sha: sha}
  end

  defp create_tree(repo, base_tree, blobs, req_options) do
    body = %{base_tree: base_tree, tree: blobs}

    case request(:post, "/repos/#{repo}/git/trees", body, req_options) do
      {:ok, %{"sha" => sha}} -> {:ok, sha}
      {:ok, other} -> {:error, {:tree_failed, other}}
      {:error, reason} -> {:error, reason}
    end
  end

  defp create_commit(repo, message, tree, parent, req_options) do
    body = %{message: message, tree: tree, parents: [parent]}

    case request(:post, "/repos/#{repo}/git/commits", body, req_options) do
      {:ok, %{"sha" => sha}} -> {:ok, sha}
      {:ok, other} -> {:error, {:commit_failed, other}}
      {:error, reason} -> {:error, reason}
    end
  end

  defp create_branch(repo, branch, sha, req_options) do
    body = %{ref: "refs/heads/#{branch}", sha: sha}

    case request(:post, "/repos/#{repo}/git/refs", body, req_options) do
      {:ok, _} ->
        :ok

      {:error, {422, _}} ->
        # Branch already exists: move it to the new commit.
        case request(
               :patch,
               "/repos/#{repo}/git/refs/heads/#{branch}",
               %{sha: sha, force: true},
               req_options
             ) do
          {:ok, _} -> :ok
          {:error, reason} -> {:error, reason}
        end

      {:error, reason} ->
        {:error, reason}
    end
  end

  defp create_pull_request(repo, branch, base, title, body, opts, req_options) do
    payload = %{title: title, head: branch, base: base, body: body}

    payload =
      if Keyword.get(opts, :draft, false), do: Map.put(payload, :draft, true), else: payload

    case request(:post, "/repos/#{repo}/pulls", payload, req_options) do
      {:ok, pr} when is_map(pr) ->
        {:ok, pr}

      {:error, {422, %{"errors" => [%{"message" => msg} | _]}}} ->
        {:error, {:pr_failed, msg}}

      {:error, reason} ->
        {:error, reason}
    end
  end

  # -- Req plumbing --------------------------------------------------------

  defp get_json(path, req_options, extractor) do
    case request(:get, path, nil, req_options) do
      {:ok, body} ->
        value = extractor.(body)
        if value, do: {:ok, value}, else: {:error, {:unexpected_response, body}}

      {:error, reason} ->
        {:error, reason}
    end
  end

  defp request(method, path, body, req_options) do
    base_url = Application.get_env(:fleet_admin, :github_api_base_url, "https://api.github.com")

    req_options =
      Keyword.merge(Application.get_env(:fleet_admin, :github_req_options, []), req_options)

    req =
      Req.new(
        base_url: base_url,
        method: method,
        url: path,
        headers: headers(),
        retry: false
      )
      |> maybe_json(body)
      |> Req.merge(req_options)

    case Req.request(req) do
      {:ok, %{status: status, body: response_body}} when status in 200..299 ->
        {:ok, response_body}

      {:ok, %{status: status, body: response_body}} ->
        {:error, {status, response_body}}

      {:error, reason} ->
        {:error, reason}
    end
  end

  defp maybe_json(req, nil), do: req
  defp maybe_json(req, body), do: Req.merge(req, json: body)

  defp headers do
    token = Application.get_env(:fleet_admin, :github_token)

    [
      {"accept", @github_accept},
      {"x-github-api-version", @github_version},
      {"user-agent", "fleet-admin"}
    ]
    |> maybe_auth_header(token)
  end

  defp maybe_auth_header(headers, token) when is_binary(token) and token != "",
    do: [{"authorization", "Bearer " <> token} | headers]

  defp maybe_auth_header(headers, _), do: headers
end
