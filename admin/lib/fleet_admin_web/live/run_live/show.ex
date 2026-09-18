defmodule FleetAdminWeb.RunLive.Show do
  @moduledoc "Single run detail: iterations, PR, audit events (plan §11)."

  use FleetAdminWeb, :live_view

  alias FleetAdmin.Ledger

  @impl true
  def mount(%{"id" => id}, _session, socket) do
    if connected?(socket), do: Ledger.subscribe()

    run = Ledger.get_run_with_details!(id)

    {:ok,
     socket
     |> assign(:page_title, "Run #{run.issue_key}")
     |> assign(:run, run)
     |> assign(:audit_empty?, run.audit_events == [])
     |> stream(:iterations, run.iterations)
     |> stream(:audit_events, run.audit_events)}
  end

  @impl true
  def handle_info({:run_ingested, %{id: id}}, %{assigns: %{run: %{id: id}}} = socket) do
    run = Ledger.get_run_with_details!(id)

    {:noreply,
     socket
     |> assign(:run, run)
     |> assign(:audit_empty?, run.audit_events == [])
     |> stream(:iterations, run.iterations, reset: true)
     |> stream(:audit_events, run.audit_events, reset: true)}
  end

  def handle_info({:run_ingested, _other}, socket), do: {:noreply, socket}

  defp format_ts(nil), do: "—"
  defp format_ts(dt), do: Calendar.strftime(dt, "%Y-%m-%d %H:%M:%S UTC")

  defp status_class("succeeded"), do: "badge badge-success"
  defp status_class("no_changes"), do: "badge badge-ghost"
  defp status_class("running"), do: "badge badge-info"
  defp status_class("verify_failed"), do: "badge badge-warning"
  defp status_class("failed"), do: "badge badge-error"
  defp status_class(_), do: "badge badge-ghost"

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <.header>
        <%= if @run.issue_key do %>
          {@run.issue_key} <span class={status_class(@run.status)}>{@run.status}</span>
        <% else %>
          Run #{@run.id}
        <% end %>
        <:subtitle>
          <a :if={@run.repo} href={"https://github.com/#{@run.repo}"} target="_blank" class="link">
            {@run.repo}
          </a>
        </:subtitle>
        <:actions>
          <.link navigate={~p"/"} class="btn btn-ghost btn-sm">Back</.link>
        </:actions>
      </.header>

      <p :if={@run.error} id="run-error" class="alert alert-error mb-6">
        {@run.error}
      </p>

      <.list>
        <:item title="Source">{@run.source || "—"}</:item>
        <:item title="Branch">{@run.branch || "—"}</:item>
        <:item title="Tool">{@run.tool || "—"}</:item>
        <:item title="Platform">{@run.platform || "—"}</:item>
        <:item title="Started">{format_ts(@run.started_at)}</:item>
        <:item title="Finished">{format_ts(@run.finished_at)}</:item>
        <:item title="PR">
          <.link :if={@run.pr_url} href={@run.pr_url} target="_blank" class="link link-primary">
            {@run.pr_url}
          </.link>
          <span :if={!@run.pr_url}>—</span>
        </:item>
        <:item title="Jenkins build">
          <.link
            :if={@run.build_url}
            id="run-build"
            href={@run.build_url}
            target="_blank"
            rel="noopener"
            class="link link-primary"
          >
            {if @run.build_number, do: "build ##{@run.build_number}", else: "build"}
          </.link>
          <span :if={!@run.build_url}>—</span>
        </:item>
      </.list>

      <h2 class="mt-8 mb-2 text-base font-semibold">Iterations</h2>
      <.table id="iterations" rows={@streams.iterations}>
        <:col :let={{_id, iter}} label="#">{iter.n}</:col>
        <:col :let={{_id, iter}} label="Agent exit">{iter.agent_exit}</:col>
        <:col :let={{_id, iter}} label="Verify exit">{iter.verify_exit}</:col>
        <:col :let={{_id, iter}} label="Prompt">
          <details>
            <summary class="cursor-pointer text-base-content/70">show</summary>
            <pre class="whitespace-pre-wrap text-xs">{iter.prompt}</pre>
          </details>
        </:col>
      </.table>

      <h2 class="mt-8 mb-2 text-base font-semibold">Audit events</h2>
      <p :if={@audit_empty?} class="text-sm text-base-content/60">
        No audit events recorded.
      </p>
      <.table id="audit_events" rows={@streams.audit_events}>
        <:col :let={{_id, event}} label="Timestamp">{format_ts(event.ts)}</:col>
        <:col :let={{_id, event}} label="Severity">{event.severity}</:col>
        <:col :let={{_id, event}} label="Action">{event.action}</:col>
        <:col :let={{_id, event}} label="Detail">
          <pre class="whitespace-pre-wrap text-xs">{event.detail}</pre>
        </:col>
      </.table>
    </Layouts.app>
    """
  end
end
