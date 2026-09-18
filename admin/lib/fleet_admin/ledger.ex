defmodule FleetAdmin.Ledger do
  @moduledoc """
  Run ledger: ingest API + queries + live PubSub broadcast.

  The Jenkins dispatcher POSTs `run.started`, `run.finished` and (P5)
  `audit.event` payloads to `/api/ingest`; this context persists them and
  broadcasts on the `"runs"` topic so the LiveView dashboard updates live.
  """

  import Ecto.Query

  alias FleetAdmin.Repo
  alias FleetAdmin.Ledger.{AuditEvent, Iteration, Pr, Run}
  alias FleetAdmin.Urls

  @topic "runs"

  # -- queries -------------------------------------------------------------

  def list_runs(opts \\ []) do
    limit = Keyword.get(opts, :limit, 100)

    Run
    |> maybe_filter(:status, opts[:status])
    |> maybe_filter(:source, opts[:source])
    |> order_by(desc: :inserted_at)
    |> limit(^limit)
    |> Repo.all()
  end

  def get_run!(id), do: Repo.get!(Run, id)

  @doc "Run counts grouped by status, for the Prometheus metrics endpoint."
  def status_counts do
    Repo.all(from(r in Run, group_by: r.status, select: {r.status, count(r.id)}))
    |> Map.new()
  end

  def get_run_with_details!(id) do
    Repo.get!(Run, id)
    |> Repo.preload([:iterations, :prs, :audit_events])
  end

  defp maybe_filter(query, _field, nil), do: query
  defp maybe_filter(query, field, value), do: where(query, [r], field(r, ^field) == ^value)

  # -- live updates --------------------------------------------------------

  def subscribe, do: Phoenix.PubSub.subscribe(FleetAdmin.PubSub, @topic)

  defp broadcast(run) do
    Phoenix.PubSub.broadcast(FleetAdmin.PubSub, @topic, {:run_ingested, run})
    run
  end

  # -- ingest --------------------------------------------------------------

  def ingest_event(%{"event" => "run.started"} = payload), do: ingest_started(payload)
  def ingest_event(%{"event" => "run.finished"} = payload), do: ingest_finished(payload)
  def ingest_event(%{"event" => "audit.event"} = payload), do: ingest_audit(payload)
  def ingest_event(%{"event" => other}), do: {:error, {:unknown_event, other}}
  def ingest_event(_payload), do: {:error, :missing_event}

  defp ingest_started(payload) do
    attrs = %{
      external_id: external_id(payload),
      source: get_in(payload, ["issue", "source"]),
      issue_key: get_in(payload, ["issue", "key"]),
      repo: payload["repo"],
      branch: payload["branch"],
      status: "running",
      tool: payload["tool"],
      platform: payload["platform"],
      started_at: now()
    }

    with {:ok, run} <- upsert_run(attrs) do
      {:ok, broadcast(run)}
    end
  end

  defp ingest_finished(payload) do
    attrs = %{
      external_id: external_id(payload),
      source: get_in(payload, ["issue", "source"]),
      issue_key: get_in(payload, ["issue", "key"]),
      repo: payload["repo"],
      branch: payload["branch"],
      commit: payload["commit"],
      pr_url: payload["pr_url"],
      reply_url: payload["reply_url"],
      mode: payload["mode"],
      comment_url: payload["comment_url"],
      comment_command: payload["comment_command"],
      status: payload["status"] || "succeeded",
      tool: payload["tool"],
      platform: payload["platform"],
      cost: payload["cost"],
      error: payload["error"],
      build_url: Urls.normalize(payload["build_url"]),
      build_number: payload["build_number"],
      finished_at: now()
    }

    with {:ok, run} <- upsert_run(attrs) do
      replace_iterations(run, payload["iterations"] || [])
      maybe_put_pr(run, payload)
      {:ok, broadcast(run)}
    end
  end

  defp ingest_audit(payload) do
    run =
      case external_id(payload) do
        nil -> nil
        ext -> Repo.get_by(Run, external_id: ext)
      end

    attrs = %{
      run_id: run && run.id,
      ts: parse_ts(payload["ts"]),
      severity: payload["severity"],
      action: payload["action"] || payload["type"],
      detail: payload["detail"] || payload["msg"],
      container: payload["container"]
    }

    %AuditEvent{}
    |> AuditEvent.changeset(attrs)
    |> Repo.insert()
    |> case do
      {:ok, event} ->
        if run, do: broadcast(run)
        {:ok, event}

      error ->
        error
    end
  end

  # -- helpers -------------------------------------------------------------

  defp upsert_run(attrs) do
    existing = Repo.get_by(Run, external_id: attrs.external_id)

    (existing || %Run{})
    |> Run.changeset(attrs)
    |> Repo.insert_or_update()
  end

  defp replace_iterations(_run, []), do: :ok

  defp replace_iterations(run, iterations) do
    Repo.delete_all(from(i in Iteration, where: i.run_id == ^run.id))

    iterations
    |> Enum.with_index(1)
    |> Enum.each(fn {iter, index} ->
      %Iteration{}
      |> Iteration.changeset(%{
        run_id: run.id,
        n: iter["n"] || index,
        prompt: iter["prompt"],
        agent_exit: get_in(iter, ["agent", "exit_code"]),
        verify_exit: get_in(iter, ["verify", "exit_code"]),
        log_ref: iter["log_ref"]
      })
      |> Repo.insert!()
    end)

    :ok
  end

  defp maybe_put_pr(run, %{"pr_url" => url}) when is_binary(url) and url != "" do
    attrs = %{run_id: run.id, url: url, state: "open", number: pr_number(url)}
    existing = Repo.get_by(Pr, run_id: run.id, url: url)

    (existing || %Pr{})
    |> Pr.changeset(attrs)
    |> Repo.insert_or_update()
  end

  defp maybe_put_pr(_run, _payload), do: :ok

  defp pr_number(url) do
    case Regex.run(~r{/pull/(\d+)}, url) do
      [_, n] -> String.to_integer(n)
      _ -> nil
    end
  end

  def external_id(payload) do
    cond do
      is_binary(payload["external_id"]) and payload["external_id"] != "" ->
        payload["external_id"]

      true ->
        key = get_in(payload, ["issue", "key"]) || payload["issue_key"]
        repo = payload["repo"]
        branch = payload["branch"]

        cond do
          key && repo && branch -> "#{repo}##{key}@#{branch}"
          key && repo -> "#{repo}##{key}"
          true -> nil
        end
    end
  end

  defp parse_ts(nil), do: now()

  defp parse_ts(ts) when is_binary(ts) do
    case DateTime.from_iso8601(ts) do
      {:ok, dt, _offset} -> DateTime.to_naive(dt)
      _ -> now()
    end
  end

  defp parse_ts(_), do: now()

  defp now, do: DateTime.utc_now() |> DateTime.to_naive()
end
