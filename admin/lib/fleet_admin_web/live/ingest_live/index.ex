defmodule FleetAdminWeb.IngestLive.Index do
  @moduledoc "Ingest log: PM webhooks, normalization and routing decisions."

  use FleetAdminWeb, :live_view

  alias FleetAdmin.Ledger

  @sources ~w(jira linear github)
  @statuses ~w(received ok filtered error)

  @impl true
  def mount(_params, _session, socket) do
    if connected?(socket), do: Ledger.subscribe_ingest()

    events = Ledger.list_ingest_events()

    {:ok,
     socket
     |> assign(:page_title, "Ingest")
     |> assign(:empty?, events == [])
     |> assign(:filter_form, to_form(%{"source" => "", "status" => ""}, as: :filter))
     |> stream(:events, events)}
  end

  @impl true
  def handle_info({:ingest_recorded, event}, socket) do
    {:noreply,
     socket
     |> assign(:empty?, false)
     |> stream_insert(:events, event, at: 0)}
  end

  @impl true
  def handle_event("filter", %{"filter" => filter}, socket) do
    opts =
      []
      |> put_if(:source, blank(filter["source"]))
      |> put_if(:status, blank(filter["status"]))

    events = Ledger.list_ingest_events(opts)

    {:noreply,
     socket
     |> assign(:empty?, events == [])
     |> stream(:events, events, reset: true)}
  end

  defp put_if(opts, _key, nil), do: opts
  defp put_if(opts, key, value), do: Keyword.put(opts, key, value)

  defp blank(value) when value in [nil, ""], do: nil
  defp blank(value), do: value

  defp source_options, do: Enum.map(@sources, &{&1, &1})
  defp status_options, do: Enum.map(@statuses, &{&1, &1})

  defp status_class("received"), do: "badge badge-info badge-sm"
  defp status_class("ok"), do: "badge badge-success badge-sm"
  defp status_class("filtered"), do: "badge badge-ghost badge-sm"
  defp status_class("error"), do: "badge badge-error badge-sm"
  defp status_class(_), do: "badge badge-ghost badge-sm"

  defp format_ts(nil), do: "—"
  defp format_ts(dt), do: Calendar.strftime(dt, "%Y-%m-%d %H:%M:%S UTC")

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <.header>
        Ingest log
        <:subtitle>PM webhooks and how they normalized and routed.</:subtitle>
        <:actions>
          <.link navigate={~p"/trigger"} class="btn btn-ghost btn-sm">Trigger a run</.link>
        </:actions>
      </.header>

      <.form for={@filter_form} id="ingest-filter" phx-change="filter" class="mb-6 flex gap-4">
        <.input
          field={@filter_form[:source]}
          type="select"
          label="Source"
          prompt="All sources"
          options={source_options()}
        />
        <.input
          field={@filter_form[:status]}
          type="select"
          label="Status"
          prompt="All statuses"
          options={status_options()}
        />
      </.form>

      <p :if={@empty?} id="ingest-empty" class="text-sm text-base-content/70">
        No ingest events yet. Send a webhook (or use the Trigger page) to see how it
        normalizes and routes.
      </p>

      <.table :if={!@empty?} id="ingest_events" rows={@streams.events}>
        <:col :let={{_id, event}} label="Time">{format_ts(event.inserted_at)}</:col>
        <:col :let={{_id, event}} label="Event">
          <span class="badge badge-ghost badge-sm">{event.event}</span>
        </:col>
        <:col :let={{_id, event}} label="Source">{event.source || "—"}</:col>
        <:col :let={{_id, event}} label="Webhook">{event.webhook_event || "—"}</:col>
        <:col :let={{_id, event}} label="Status">
          <span class={status_class(event.status)}>{event.status}</span>
        </:col>
        <:col :let={{_id, event}} label="Route">
          <span :if={event.repo}>{event.project} → {event.repo}</span>
          <span :if={!event.repo}>{event.project || "—"}</span>
        </:col>
        <:col :let={{_id, event}} label="Issue">{event.issue_key || "—"}</:col>
        <:col :let={{_id, event}} label="Detail">
          <details :if={event.detail || event.reason || event.payload}>
            <summary class="cursor-pointer text-base-content/70">
              {event.reason || "show"}
            </summary>
            <pre :if={event.detail} class="whitespace-pre-wrap text-xs">{event.detail}</pre>
            <pre :if={event.payload} class="whitespace-pre-wrap text-xs text-base-content/60">{event.payload}</pre>
          </details>
          <span :if={!event.detail && !event.reason && !event.payload}>—</span>
        </:col>
      </.table>
    </Layouts.app>
    """
  end
end
