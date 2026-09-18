# Sample fleet runs for local development / demos.
#
#     mix run priv/repo/seeds.exs
#
# Idempotent: re-running upserts by external_id.

alias FleetAdmin.Ledger

if Ledger.list_runs(limit: 1) == [] do
  [
    %{
      "event" => "run.finished",
      "issue" => %{"source" => "jira", "key" => "ENG-101"},
      "repo" => "acme/engine-api",
      "branch" => "fleet/ENG-101",
      "status" => "succeeded",
      "tool" => "claude",
      "platform" => "linux",
      "pr_url" => "https://github.com/acme/engine-api/pull/101",
      "build_url" => "http://localhost:8080/job/fleet-dispatcher/1/",
      "build_number" => 1,
      "iterations" => [
        %{
          "n" => 1,
          "prompt" => "Fix the login 500 on plus-sign passwords.",
          "agent" => %{"exit_code" => 0},
          "verify" => %{"exit_code" => 1}
        },
        %{
          "n" => 2,
          "prompt" => "Fix the login 500. Previous verify failed:\n...",
          "agent" => %{"exit_code" => 0},
          "verify" => %{"exit_code" => 0}
        }
      ]
    },
    %{
      "event" => "run.finished",
      "issue" => %{"source" => "jira", "key" => "ENG-102"},
      "repo" => "acme/engine-web",
      "branch" => "fleet/ENG-102",
      "status" => "verify_failed",
      "tool" => "opencode",
      "platform" => "linux",
      "error" => "verify.sh still failing after 3 iteration(s)"
    }
  ]
  |> Enum.each(&Ledger.ingest_event/1)

  # A couple of audit events on the first run.
  Enum.each(
    [
      %{
        "event" => "audit.event",
        "repo" => "acme/engine-api",
        "issue_key" => "ENG-101",
        "branch" => "fleet/ENG-101",
        "severity" => "info",
        "type" => "exec",
        "msg" => "npm ci",
        "container" => "coi-seed-1"
      },
      %{
        "event" => "audit.event",
        "repo" => "acme/engine-api",
        "issue_key" => "ENG-101",
        "branch" => "fleet/ENG-101",
        "severity" => "high",
        "type" => "net",
        "msg" => "blocked egress to 10.0.0.5:22",
        "container" => "coi-seed-1"
      }
    ],
    &Ledger.ingest_event/1
  )

  IO.puts("Seeded sample fleet runs.")
else
  IO.puts("Runs already present; skipping seed.")
end
