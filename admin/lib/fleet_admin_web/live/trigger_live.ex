defmodule FleetAdminWeb.TriggerLive do
  @moduledoc "Manually fire a webhook-like event to start a fleet run (for testing)."

  use FleetAdminWeb, :live_view

  alias FleetAdmin.Trigger

  @sample_jira """
  {
    "webhookEvent": "jira:issue_created",
    "issue": {
      "key": "ENG-999",
      "self": "https://acme.atlassian.net/rest/api/2/issue/999",
      "fields": {
        "summary": "Test run from the admin panel",
        "description": "Manual webhook-like trigger. Replace with a real issue to exercise the pipeline.",
        "issuetype": { "name": "Task" },
        "labels": ["agent"],
        "project": { "key": "ENG" },
        "components": [{ "name": "backend" }],
        "reporter": { "displayName": "fleet admin" }
      }
    }
  }
  """

  @sample_github_comment """
  {
    "action": "created",
    "issue": {
      "number": 14,
      "title": "A pull request",
      "pull_request": { "url": "https://api.github.com/repos/OWNER/REPO/pulls/14" },
      "user": { "login": "you" }
    },
    "comment": {
      "id": 1,
      "body": "/agent describe what the agent should do",
      "html_url": "https://github.com/OWNER/REPO/pull/14#issuecomment-1",
      "author_association": "OWNER",
      "user": { "login": "you", "type": "User" }
    },
    "repository": { "full_name": "OWNER/REPO" }
  }
  """

  defp presets do
    %{
      "jira" => %{
        "source" => "jira",
        "event" => "jira:issue_created",
        "payload" => @sample_jira
      },
      "github_pr_comment" => %{
        "source" => "github",
        "event" => "issue_comment",
        "payload" => @sample_github_comment
      }
    }
  end

  @impl true
  def mount(_params, _session, socket) do
    {:ok,
     socket
     |> assign(:page_title, "Trigger")
     |> assign(:configured?, Trigger.configured?())
     |> assign(:endpoint, Trigger.endpoint("jira"))
     |> assign(:json_error, nil)
     |> assign(:result, nil)
     |> assign_form(%{})}
  end

  @impl true
  def handle_event("validate", %{"trigger" => params}, socket) do
    {:noreply,
     socket
     |> assign_json_error(params["payload"])
     |> assign_form(params)}
  end

  def handle_event("submit", %{"trigger" => params}, socket) do
    source = params["source"]
    event = params["event"]
    dry_run = params["dry_run"] in ["true", "on", true]

    socket = assign_json_error(socket, params["payload"])

    case Trigger.trigger(source, event, params["payload"], dry_run: dry_run) do
      {:ok, result} ->
        {:noreply,
         socket
         |> assign(:result, {:ok, result})
         |> put_flash(:info, flash_message(result))}

      {:error, reason} ->
        {:noreply,
         socket
         |> assign(:result, {:error, reason})
         |> put_flash(:error, "Trigger failed: " <> format_reason(reason))}
    end
  end

  def handle_event("preset", %{"kind" => kind}, socket) do
    case presets()[kind] do
      nil ->
        {:noreply, socket}

      preset ->
        {:noreply,
         socket
         |> assign(:endpoint, Trigger.endpoint(preset["source"]))
         |> assign(:json_error, nil)
         |> assign(:result, nil)
         |> assign_form(preset)}
    end
  end

  defp assign_form(socket, params) do
    defaults = %{
      "source" => "jira",
      "event" => "jira:issue_created",
      "payload" => @sample_jira,
      "dry_run" => false
    }

    assign(socket, :form, to_form(Map.merge(defaults, params), as: :trigger))
  end

  defp assign_json_error(socket, payload) do
    case Jason.decode(to_string(payload || "")) do
      {:ok, _} -> assign(socket, :json_error, nil)
      {:error, _} -> assign(socket, :json_error, "Payload is not valid JSON")
    end
  end

  defp flash_message(%{dry_run: true}), do: "Dry run preview ready"
  defp flash_message(%{status: status}), do: "Webhook sent (HTTP #{status})"

  defp format_reason(:invalid_json), do: "payload is not valid JSON"
  defp format_reason(:payload_must_be_object), do: "payload must be a JSON object"
  defp format_reason(:not_configured), do: "no webhook endpoint configured"
  defp format_reason({:unknown_source, source}), do: "unknown source: #{source}"
  defp format_reason(other), do: inspect(other)

  defp format_body(body) when is_binary(body), do: body
  defp format_body(body), do: Jason.encode!(body, pretty: true)

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <.header>
        Trigger a run
        <:subtitle>
          Send a webhook-like event to the configured dispatcher endpoint. Use this
          to test the pipeline without a real PM-tool webhook.
        </:subtitle>
      </.header>

      <p :if={!@configured?} id="trigger-unconfigured" class="alert alert-warning mb-6">
        Set <code>FLEET_WEBHOOK_URL</code> (and optionally <code>FLEET_WEBHOOK_TOKEN</code>)
        to enable triggering.
      </p>

      <p :if={Layouts.jenkins_url()} class="mb-2 text-sm text-base-content/70">
        Jenkins master:
        <a
          id="jenkins-master"
          href={Layouts.jenkins_url()}
          target="_blank"
          rel="noopener"
          class="link"
        >
          {Layouts.jenkins_url()}
        </a>
      </p>

      <p :if={@configured?} class="mb-4 text-sm text-base-content/70">
        Endpoint: <code id="trigger-endpoint">{@endpoint}</code>
      </p>

      <div class="mb-4 flex items-center gap-2">
        <span class="text-sm text-base-content/70">Preset:</span>
        <button
          id="preset-jira"
          type="button"
          class="btn btn-sm btn-outline"
          phx-click="preset"
          phx-value-kind="jira"
        >
          Jira issue
        </button>
        <button
          id="preset-github-comment"
          type="button"
          class="btn btn-sm btn-outline"
          phx-click="preset"
          phx-value-kind="github_pr_comment"
        >
          GitHub PR comment
        </button>
      </div>

      <.form for={@form} id="trigger-form" phx-change="validate" phx-submit="submit" class="space-y-4">
        <.input
          field={@form[:source]}
          type="select"
          label="Source"
          options={Enum.map(Trigger.sources(), &{&1, &1})}
        />
        <.input field={@form[:event]} type="text" label="Event" />
        <.input field={@form[:payload]} type="textarea" label="Payload (JSON)" rows="14" />
        <.input
          field={@form[:dry_run]}
          type="checkbox"
          label="Dry run (preview the request without sending it)"
        />

        <p :if={@json_error} id="trigger-json-error" class="text-sm text-error">{@json_error}</p>

        <.button id="trigger-submit" phx-disable-with="Sending..." disabled={!@configured?}>
          Trigger run
        </.button>
      </.form>

      <div :if={@result} id="trigger-result" class="mt-8">
        <%= case @result do %>
          <% {:ok, %{dry_run: true} = preview} -> %>
            <div class="alert">
              <p class="font-semibold">Dry run preview</p>
              <p class="text-sm">
                POST <code>{preview.url}</code>
              </p>
              <pre class="whitespace-pre-wrap text-xs">{Jason.encode!(preview.body, pretty: true)}</pre>
            </div>
          <% {:ok, result} -> %>
            <div class="alert alert-success">
              <p>Request sent: HTTP {result.status}</p>
              <pre class="whitespace-pre-wrap text-xs">{format_body(result.body)}</pre>
            </div>
          <% {:error, reason} -> %>
            <p class="alert alert-error">Failed: {format_reason(reason)}</p>
        <% end %>
      </div>
    </Layouts.app>
    """
  end
end
