defmodule FleetAdminWeb.GitOpsLive do
  @moduledoc "GitOps config editing: open a PR with a file change (plan §11)."

  use FleetAdminWeb, :live_view

  alias FleetAdmin.GitOps

  @impl true
  def mount(_params, _session, socket) do
    {:ok,
     socket
     |> assign(:page_title, "GitOps")
     |> assign(:configured?, GitOps.configured?())
     |> assign(:result, nil)
     |> assign_form(%{})}
  end

  @impl true
  def handle_event("validate", %{"gitops" => params}, socket) do
    {:noreply, assign_form(socket, params)}
  end

  def handle_event("submit", %{"gitops" => params}, socket) do
    files = [%{"path" => params["path"], "content" => params["content"]}]
    opts = if params["draft"] in ["true", "on"], do: [draft: true], else: []

    case GitOps.open_pr(
           params["repo"],
           params["base"],
           files,
           params["title"],
           params["body"],
           opts
         ) do
      {:ok, result} ->
        {:noreply,
         socket
         |> assign(:result, {:ok, result})
         |> put_flash(:info, "Opened PR ##{result.number}")}

      {:error, reason} ->
        {:noreply,
         socket
         |> assign(:result, {:error, reason})
         |> put_flash(:error, "Could not open PR: #{inspect(reason)}")}
    end
  end

  defp assign_form(socket, params) do
    defaults = %{
      "repo" => "acme/fleet-config",
      "base" => "main",
      "path" => "registry.yaml",
      "title" => "fleet: update config",
      "content" => "",
      "body" => "Automated config change from the fleet admin panel.",
      "draft" => false
    }

    assign(socket, :form, to_form(Map.merge(defaults, params), as: :gitops))
  end

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <.header>
        GitOps config write-back
        <:subtitle>
          Commit a file change to a branch and open a pull request. No direct writes.
        </:subtitle>
      </.header>

      <p :if={!@configured?} id="gitops-unconfigured" class="alert alert-warning mb-6">
        Set <code>GITHUB_TOKEN</code> on the panel to enable GitOps writes.
      </p>

      <.form for={@form} id="gitops-form" phx-change="validate" phx-submit="submit" class="space-y-4">
        <.input field={@form[:repo]} type="text" label="Repository (owner/name)" />
        <.input field={@form[:base]} type="text" label="Base branch" />
        <.input field={@form[:path]} type="text" label="File path" />
        <.input field={@form[:title]} type="text" label="PR title" />
        <.input field={@form[:content]} type="textarea" label="New file content" rows="10" />
        <.input field={@form[:body]} type="textarea" label="PR body" rows="3" />
        <.input field={@form[:draft]} type="checkbox" label="Open as draft" />
        <.button id="gitops-submit" phx-disable-with="Opening PR...">
          Open pull request
        </.button>
      </.form>

      <div :if={@result} id="gitops-result" class="mt-8">
        <%= case @result do %>
          <% {:ok, result} -> %>
            <p class="alert alert-success">
              Opened <.link href={result.pr_url} target="_blank" class="link">{result.pr_url}</.link>
              on branch <code>{result.branch}</code>
            </p>
          <% {:error, reason} -> %>
            <p class="alert alert-error">Failed: {inspect(reason)}</p>
        <% end %>
      </div>
    </Layouts.app>
    """
  end
end
