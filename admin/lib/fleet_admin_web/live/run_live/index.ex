defmodule FleetAdminWeb.RunLive.Index do
  @moduledoc "Live run ledger (plan §11)."

  use FleetAdminWeb, :live_view

  alias FleetAdmin.Ledger

  @impl true
  def mount(_params, _session, socket) do
    if connected?(socket), do: Ledger.subscribe()

    runs = Ledger.list_runs()

    {:ok,
     socket
     |> assign(:page_title, "Runs")
     |> assign(:status_filter, nil)
     |> assign(:empty?, runs == [])
     |> assign(:filter_form, to_form(%{"status" => ""}, as: :filter))
     |> stream(:runs, runs)}
  end

  @impl true
  def handle_info({:run_ingested, run}, socket) do
    {:noreply, socket |> assign(:empty?, false) |> stream_insert(:runs, run)}
  end

  @impl true
  def handle_event("filter", %{"filter" => %{"status" => status}}, socket) do
    status = if status in [nil, ""], do: nil, else: status
    runs = Ledger.list_runs(status: status)

    {:noreply,
     socket
     |> assign(:status_filter, status)
     |> assign(:empty?, runs == [])
     |> stream(:runs, runs, reset: true)}
  end

  defp status_class("succeeded"), do: "badge badge-success badge-sm"
  defp status_class("no_changes"), do: "badge badge-ghost badge-sm"
  defp status_class("running"), do: "badge badge-info badge-sm"
  defp status_class("verify_failed"), do: "badge badge-warning badge-sm"
  defp status_class("failed"), do: "badge badge-error badge-sm"
  defp status_class(_), do: "badge badge-ghost badge-sm"

  defp status_options do
    Enum.map(Ledger.Run.statuses(), &{&1, &1})
  end

  defp format_ts(nil), do: "—"
  defp format_ts(dt), do: Calendar.strftime(dt, "%Y-%m-%d %H:%M:%S UTC")

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <.header>
        Fleet runs
        <:subtitle>Every agent run and its verification outcome.</:subtitle>
      </.header>

      <.form for={@filter_form} id="run-filter" phx-change="filter" class="mb-6">
        <.input
          field={@filter_form[:status]}
          type="select"
          label="Status"
          prompt="All statuses"
          options={status_options()}
        />
      </.form>

      <p :if={@empty?} id="runs-empty" class="text-sm text-base-content/70">
        No runs yet. Configure the Jenkins webhook to get started.
      </p>

      <.table
        :if={!@empty?}
        id="runs"
        rows={@streams.runs}
        row_click={fn {_id, run} -> JS.navigate(~p"/runs/#{run.id}") end}
      >
        <:col :let={{_id, run}} label="Issue">{run.issue_key}</:col>
        <:col :let={{_id, run}} label="Repo">{run.repo}</:col>
        <:col :let={{_id, run}} label="Tool">{run.tool}</:col>
        <:col :let={{_id, run}} label="Status">
          <span class={status_class(run.status)}>{run.status}</span>
        </:col>
        <:col :let={{_id, run}} label="PR">
          <.link :if={run.pr_url} href={run.pr_url} target="_blank" class="link link-primary">
            view
          </.link>
          <span :if={!run.pr_url} class="text-base-content/40">—</span>
        </:col>
        <:col :let={{_id, run}} label="Finished">{format_ts(run.finished_at)}</:col>
        <:action :let={{_id, run}}>
          <.link
            :if={run.build_url}
            id={"build-#{run.id}"}
            href={run.build_url}
            target="_blank"
            rel="noopener"
            class="link link-primary"
          >
            Jenkins
          </.link>
        </:action>
      </.table>
    </Layouts.app>
    """
  end
end
