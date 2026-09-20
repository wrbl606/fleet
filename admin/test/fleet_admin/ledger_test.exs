defmodule FleetAdmin.LedgerTest do
  use FleetAdmin.DataCase, async: false

  alias FleetAdmin.Ledger

  @finished %{
    "event" => "run.finished",
    "issue" => %{"source" => "jira", "key" => "ENG-1"},
    "repo" => "acme/engine-api",
    "branch" => "fleet/ENG-1",
    "status" => "succeeded",
    "tool" => "claude",
    "pr_url" => "https://github.com/acme/engine-api/pull/7",
    "build_url" => "https://jenkins.example/job/fleet-dispatcher/7/",
    "build_number" => 7,
    "iterations" => [
      %{
        "n" => 1,
        "prompt" => "do it",
        "agent" => %{"exit_code" => 0},
        "verify" => %{"exit_code" => 1}
      },
      %{
        "n" => 2,
        "prompt" => "retry",
        "agent" => %{"exit_code" => 0},
        "verify" => %{"exit_code" => 0}
      }
    ]
  }

  test "ingests a finished run with iterations and a PR" do
    assert {:ok, run} = Ledger.ingest_event(@finished)
    assert run.status == "succeeded"
    assert run.external_id == "acme/engine-api#ENG-1@fleet/ENG-1"
    assert run.pr_url =~ "/pull/7"
    assert run.build_url == "https://jenkins.example/job/fleet-dispatcher/7/"
    assert run.build_number == 7
    assert run.finished_at

    run = Ledger.get_run_with_details!(run.id)
    assert length(run.iterations) == 2
    assert run.iterations |> Enum.map(& &1.verify_exit) |> Enum.sort() == [0, 1]
    assert [pr] = run.prs
    assert pr.number == 7
  end

  test "upserts the same run and replaces iterations" do
    {:ok, run} = Ledger.ingest_event(@finished)

    updated =
      Map.merge(@finished, %{
        "status" => "verify_failed",
        "pr_url" => nil,
        "iterations" => [
          %{"n" => 1, "agent" => %{"exit_code" => 0}, "verify" => %{"exit_code" => 1}}
        ]
      })

    assert {:ok, run2} = Ledger.ingest_event(updated)
    assert run2.id == run.id
    assert run2.status == "verify_failed"

    details = Ledger.get_run_with_details!(run.id)
    assert length(details.iterations) == 1
  end

  test "separates PR-comment runs by comment id" do
    base = %{
      "event" => "run.finished",
      "issue" => %{"source" => "github", "key" => "o/r#14", "comment_id" => 1},
      "repo" => "o/r",
      "branch" => "feature/x",
      "status" => "succeeded"
    }

    assert {:ok, first} = Ledger.ingest_event(base)
    assert {:ok, second} = Ledger.ingest_event(put_in(base, ["issue", "comment_id"], 2))

    assert first.id != second.id
    assert first.external_id =~ "#c1"
    assert second.external_id =~ "#c2"
  end

  test "honours an explicit external_id" do
    assert {:ok, run} =
             Ledger.ingest_event(%{
               "event" => "run.finished",
               "external_id" => "custom-1",
               "issue" => %{"key" => "X"},
               "repo" => "a/b",
               "branch" => "b",
               "status" => "succeeded"
             })

    assert run.external_id == "custom-1"
  end

  test "records the ingest log for webhook, normalize and resolve" do
    {:ok, webhook} =
      Ledger.ingest_event(%{
        "event" => "webhook.received",
        "source" => "jira",
        "webhook_event" => "jira:issue_created",
        "delivery" => "d1",
        "payload" => ~s({"issue":{"key":"ENG-1"}})
      })

    assert webhook.event == "webhook.received"
    assert webhook.status == "received"

    {:ok, normalized} =
      Ledger.ingest_event(%{
        "event" => "normalize.result",
        "source" => "jira",
        "webhook_event" => "jira:issue_created",
        "actionable" => true,
        "issue" => %{"key" => "ENG-1", "project" => "ENG"}
      })

    assert normalized.status == "ok"
    assert normalized.issue_key == "ENG-1"
    assert normalized.actionable
    assert normalized.detail =~ "ENG-1"

    {:ok, filtered} =
      Ledger.ingest_event(%{
        "event" => "normalize.result",
        "source" => "github",
        "actionable" => false,
        "reason" => "event filtered"
      })

    assert filtered.status == "filtered"

    {:ok, resolved} =
      Ledger.ingest_event(%{
        "event" => "resolve.result",
        "source" => "jira",
        "issue_key" => "ENG-1",
        "project" => "ENG",
        "resolution" => %{"repo" => "acme/engine", "platform" => "linux"}
      })

    assert resolved.status == "ok"
    assert resolved.repo == "acme/engine"

    {:ok, failed} =
      Ledger.ingest_event(%{
        "event" => "resolve.result",
        "source" => "jira",
        "issue_key" => "ENG-9",
        "project" => "NOPE",
        "error" => "no registry source matches"
      })

    assert failed.status == "error"
    assert failed.reason =~ "no registry"

    assert length(Ledger.list_ingest_events()) == 5
    assert [%{status: "error"}] = Ledger.list_ingest_events(status: "error")
  end

  test "ingests run.started" do
    assert {:ok, run} =
             Ledger.ingest_event(%{
               "event" => "run.started",
               "issue" => %{"key" => "ENG-2", "source" => "jira"},
               "repo" => "acme/x",
               "branch" => "fleet/ENG-2"
             })

    assert run.status == "running"
    assert run.started_at
  end

  test "ingests audit events linked to a run" do
    {:ok, run} = Ledger.ingest_event(@finished)

    assert {:ok, event} =
             Ledger.ingest_event(%{
               "event" => "audit.event",
               "repo" => "acme/engine-api",
               "issue_key" => "ENG-1",
               "branch" => "fleet/ENG-1",
               "ts" => "2026-01-01T00:00:00Z",
               "severity" => "high",
               "type" => "net",
               "msg" => "blocked egress",
               "container" => "coi-1"
             })

    assert event.run_id == run.id
    assert event.severity == "high"
    assert event.action == "net"
    assert event.detail == "blocked egress"
  end

  test "rejects unknown / malformed events" do
    assert {:error, {:unknown_event, "nope"}} = Ledger.ingest_event(%{"event" => "nope"})
    assert {:error, :missing_event} = Ledger.ingest_event(%{})
  end

  test "normalizes a schemeless build_url" do
    assert {:ok, run} =
             Ledger.ingest_event(%{
               "event" => "run.finished",
               "issue" => %{"source" => "jira", "key" => "ENG-NORM"},
               "repo" => "acme/x",
               "branch" => "fleet/ENG-NORM",
               "status" => "succeeded",
               "build_url" => "jenkins.internal:8080/job/fleet-dispatcher/9/"
             })

    assert run.build_url == "http://jenkins.internal:8080/job/fleet-dispatcher/9/"
  end

  test "list_runs filters by status" do
    {:ok, _} = Ledger.ingest_event(@finished)

    {:ok, _} =
      Ledger.ingest_event(%{
        "event" => "run.finished",
        "issue" => %{"key" => "ENG-3", "source" => "jira"},
        "repo" => "acme/x",
        "branch" => "fleet/ENG-3",
        "status" => "failed"
      })

    assert length(Ledger.list_runs()) == 2
    assert [%{status: "failed"}] = Ledger.list_runs(status: "failed")
  end
end
