defmodule WebsiteWeb.HomeLive do
  use WebsiteWeb, :live_view

  @risks [
    %{
      icon: "hero-bolt",
      title: "Prompt injection",
      detail:
        "An issue, PR comment, or repo file weaponizes the agent → it runs in a disposable sandbox with only the task repo mounted. Tokens and host are out of reach, and every change is still a human-reviewed PR."
    },
    %{
      icon: "hero-globe-alt",
      title: "Malicious repo",
      detail:
        "Egress is an allowlist, and COI domains/caps come from the trusted registry — never the repo. Untrusted repos get a hardened profile by default."
    },
    %{
      icon: "hero-arrows-pointing-out",
      title: "Repo widens its own sandbox",
      detail:
        "A repo manifest may request policy but can never exceed central coi caps or the domain allowlist. The gate fails closed."
    },
    %{
      icon: "hero-key",
      title: "Compromised agent",
      detail:
        "The agent gets no GitHub token. A separate trusted publisher stage uses a scoped token to commit and push only to the task branch."
    },
    %{
      icon: "hero-cpu-chip",
      title: "Bare-metal escape",
      detail:
        "Native runs are fail-closed: an OS sandbox (Seatbelt/PF, Windows wrapper) plus explicit repo and node allowlists — or they do not run."
    },
    %{
      icon: "hero-shield-check",
      title: "Forged webhooks",
      detail:
        "Webhooks are token-authenticated. PR-comment triggers are restricted by author association/allowlist and only ever update an existing PR branch."
    },
    %{
      icon: "hero-clock",
      title: "Runaway activity",
      detail:
        "A bounded setup → agent → verify loop with timeouts and registry caps. Every run is recorded in the ledger and ingest log; delivery is only via PR."
    }
  ]

  @stack [
    %{
      name: "Jenkins",
      tag: "control plane",
      detail:
        "Webhook ingress (Generic Webhook Trigger), node routing, and per-run credential binding."
    },
    %{
      name: "Incus + COI",
      tag: "linux sandbox",
      detail:
        "Containers-on-Incus, plus native Seatbelt/PF and Windows wrappers for allowlisted bare-metal nodes."
    },
    %{
      name: "Git + gh CLI",
      tag: "delivery",
      detail: "Checkout, scoped pushes, and pull requests — with no bespoke VCS layer."
    },
    %{
      name: "Headless agents",
      tag: "the worker",
      detail:
        "Existing CLI agents (claude, codex, opencode, …), each given only the LLM key it needs."
    },
    %{
      name: "Python fleetctl",
      tag: "dispatcher core",
      detail: "Stdlib-first, dependency-light, unit-testable and runnable outside Jenkins."
    },
    %{
      name: "Phoenix LiveView",
      tag: "admin panel",
      detail: "Run ledger, ingest log, manual trigger, and GitOps config PRs in real time."
    }
  ]

  @concepts [
    %{
      name: "registry.yaml",
      detail:
        "Trusted routing (source → repo), native allowlist, COI/native policy and resource caps. Generic examples only — it ships reusable."
    },
    %{
      name: ".fleet/",
      detail:
        "Per-repo contract: fleet.toml, prompt template, setup.sh, verify.sh, and a PR template."
    },
    %{
      name: "registry.local.yaml",
      detail:
        "Optional, git-ignored overlay for deployment-specific repos; merged over registry.yaml by fleetctl."
    },
    %{
      name: "fleetctl",
      detail: "Dispatcher core: normalize, resolve, plan, run the bounded loop, publish, notify."
    },
    %{
      name: "Runner backends",
      detail:
        "coi (Linux sandbox) and native (macOS Seatbelt / Windows wrapper), both fail-closed."
    },
    %{
      name: "PR-comment trigger",
      detail:
        "A GitHub /agent comment updates the PR branch and/or replies; policy lives in registry.yaml."
    },
    %{
      name: "Admin panel",
      detail:
        "Phoenix LiveView run ledger, ingest log, ingest API, /api/trigger, and GitOps config PRs."
    }
  ]

  @docs [
    %{name: "fleet-contract", detail: ".fleet/ contract + templating"},
    %{name: "runner-backends", detail: "COI / native backends, routing, secret injection"},
    %{name: "coi-images", detail: "Custom COI images (e.g. the Flutter profile)"},
    %{name: "security", detail: "Trust boundaries, credentials, hardening"},
    %{name: "p0-runbook", detail: "Install COI, run the P0 MVP"},
    %{name: "jenkins-node", detail: "Jenkins controller + build-node requirements"},
    %{name: "bare-metal-hardening", detail: "macOS / Windows host hardening"},
    %{name: "scale-observability", detail: "Pools, autoscaling, audit shipping, metrics"}
  ]

  @pipeline ~w(jira:webhook jenkins:gwt normalize resolve clone plan setup agent verify publish)

  @terminal_lines [
    [{"text-white/40", "$ "}, {"text-white/90", "fleetctl plan --source jira"}],
    [
      {"text-sky-400", "→ normalize"},
      {"", "  jira:issue_created   "},
      {"text-white/50", "ENG-142"}
    ],
    [{"text-sky-400", "→ resolve"}, {"", "    project ENG → acme/engine"}],
    [{"text-sky-400", "→ plan"}, {"", "       coi · linux · caps cpu=2 mem=4g"}],
    [{"text-emerald-400", "→ setup"}, {"", "      ok "}, {"text-white/40", "(12.4s)"}],
    [
      {"text-emerald-400", "→ agent"},
      {"", "      claude · "},
      {"text-amber-400", "no github token"}
    ],
    [{"text-emerald-400", "→ verify"}, {"", "     ok "}, {"text-white/40", "(27.1s)"}],
    [
      {"text-fuchsia-400", "→ publish"},
      {"", "    fleet/ENG-142 → gh pr create "},
      {"text-emerald-400", "✓"}
    ],
    [{"text-white/40", "[pr] https://github.com/acme/engine/pull/98"}]
  ]

  @dispatcher_code """
  python3 -m pip install -r requirements.txt

  python3 -m fleetctl normalize --source jira \\
      --payload-file tests/fixtures/issue-created.json

  python3 -m fleetctl plan --registry registry.yaml \\
      --repo-dir examples/sample-repo --source jira \\
      --payload-file tests/fixtures/issue-created.json \\
      --out /tmp/plan.json
  """

  @smoke_code """
  bash scripts/p0-smoke.sh

  # expected: [p0] PASS
  """

  @panel_code """
  mise install
  bash admin/start.sh --host 0.0.0.0 --port 4000

  # /        run ledger
  # /ingest  ingest log
  # /trigger manual trigger
  # /gitops  config PRs
  """

  def mount(_params, _session, socket) do
    {:ok,
     assign(socket,
       page_title: "fleet — safe remote AI implementation",
       page_description:
         "Hand real engineering tasks to an AI coding agent without trusting it. The agent runs in a locked-down sandbox on your own hardware and delivers a human-reviewed pull request.",
       risks: @risks,
       stack: @stack,
       concepts: @concepts,
       docs: @docs,
       pipeline: @pipeline,
       terminal_lines: @terminal_lines,
       dispatcher_code: @dispatcher_code,
       smoke_code: @smoke_code,
       panel_code: @panel_code
     )}
  end

  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash}>
      <.hero terminal_lines={@terminal_lines} />
      <.flow pipeline={@pipeline} />
      <.risks_section risks={@risks} />
      <.stack_section stack={@stack} />
      <.concepts_section concepts={@concepts} />
      <.quickstart
        dispatcher_code={@dispatcher_code}
        smoke_code={@smoke_code}
        panel_code={@panel_code}
      />
      <.docs_section docs={@docs} />
      <.footer />
    </Layouts.app>
    """
  end

  attr :terminal_lines, :list, required: true

  defp hero(assigns) do
    ~H"""
    <section id="top" class="mx-auto max-w-7xl px-6 pb-20 pt-20 lg:px-8 lg:pt-28">
      <div class="grid items-center gap-16 lg:grid-cols-[1.05fr_1fr]">
        <div class="min-w-0 animate-fade-up">
          <div class="mb-6 inline-flex items-center gap-2 rounded-full border border-base-content/10 bg-base-content/5 px-3 py-1.5 text-xs font-medium text-base-content/70">
            <span class="relative flex size-2">
              <span class="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-75"></span>
              <span class="relative inline-flex size-2 rounded-full bg-success"></span>
            </span>
            Safe remote implementation · phases P0–P6
          </div>

          <h1 class="text-5xl font-extrabold leading-[1.05] tracking-tight sm:text-6xl lg:text-7xl">
            Hand real tasks to an AI <span class="text-gradient"> without trusting it.</span>
          </h1>

          <p class="mt-6 max-w-xl text-lg leading-relaxed text-base-content/70">
            fleet triggers an agent from the tools your team already uses — Jira or a GitHub
            <code class="rounded bg-base-content/5 px-1.5 py-0.5 font-mono text-sm text-base-content/90">/agent</code>
            PR comment — works inside a locked-down sandbox on your own hardware, and delivers a change as an ordinary pull request for human review.
          </p>

          <p class="mt-4 max-w-xl text-base-content/50">
            The agent never holds a GitHub token, never gets open network access, and cannot widen its own permissions.
          </p>

          <div class="mt-10 flex flex-wrap items-center gap-4">
            <a
              href="#start"
              class="group inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-primary to-accent px-6 py-3 font-semibold text-primary-content shadow-lg shadow-primary/30 transition hover:shadow-xl hover:shadow-primary/40"
            >
              Run it in 5 minutes
              <.icon name="hero-arrow-right" class="size-4 transition group-hover:translate-x-0.5" />
            </a>
            <a
              href="#security"
              class="inline-flex items-center gap-2 rounded-xl border border-base-content/10 bg-base-content/5 px-6 py-3 font-semibold transition hover:border-base-content/20 hover:bg-base-content/10"
            >
              <.icon name="hero-shield-check" class="size-4" /> Threat model
            </a>
          </div>

          <div class="mt-10 flex flex-wrap gap-x-8 gap-y-4 text-sm text-base-content/50">
            <span class="inline-flex items-center gap-2"><.icon
              name="hero-lock-closed"
              class="size-4 text-success"
            /> No GitHub token for the agent</span>
            <span class="inline-flex items-center gap-2"><.icon
              name="hero-no-symbol"
              class="size-4 text-success"
            /> Fail-closed sandbox</span>
            <span class="inline-flex items-center gap-2"><.icon
              name="hero-git-pull-request"
              class="size-4 text-success"
            /> Human-reviewed delivery</span>
          </div>
        </div>

        <.terminal lines={@terminal_lines} />
      </div>
    </section>
    """
  end

  attr :lines, :list, required: true

  defp terminal(assigns) do
    ~H"""
    <div class="min-w-0 animate-fade-up [animation-delay:120ms]">
      <div class="overflow-hidden rounded-2xl border border-white/10 bg-[#0b0d17]/90 shadow-2xl shadow-black/50 backdrop-blur">
        <div class="flex items-center gap-2 border-b border-white/5 bg-white/[0.03] px-4 py-3">
          <span class="size-3 rounded-full bg-[#ff5f57]"></span>
          <span class="size-3 rounded-full bg-[#febc2e]"></span>
          <span class="size-3 rounded-full bg-[#28c840]"></span>
          <span class="ml-3 font-mono text-xs text-white/40">fleetctl · bounded run loop</span>
        </div>
        <div class="overflow-x-auto p-5 font-mono text-[13px] leading-relaxed text-white/80">
          <div :for={line <- @lines} class="whitespace-pre">
            <span :for={{class, text} <- line} class={class}>{text}</span>
          </div>
        </div>
      </div>
      <div class="mt-4 grid grid-cols-3 gap-4">
        <div class="rounded-xl border border-base-content/5 bg-base-content/[0.03] p-4">
          <div class="font-mono text-lg font-semibold text-base-content">0</div>
          <div class="text-xs text-base-content/50">GitHub tokens given to agents</div>
        </div>
        <div class="rounded-xl border border-base-content/5 bg-base-content/[0.03] p-4">
          <div class="font-mono text-lg font-semibold text-base-content">PR-only</div>
          <div class="text-xs text-base-content/50">Delivery channel</div>
        </div>
        <div class="rounded-xl border border-base-content/5 bg-base-content/[0.03] p-4">
          <div class="font-mono text-lg font-semibold text-base-content">P0–P6</div>
          <div class="text-xs text-base-content/50">Implemented phases</div>
        </div>
      </div>
    </div>
    """
  end

  attr :pipeline, :list, required: true

  defp flow(assigns) do
    ~H"""
    <section class="mx-auto max-w-7xl px-6 py-16 lg:px-8">
      <div class="rounded-3xl border border-base-content/10 bg-base-content/[0.02] p-8 lg:p-12">
        <p class="mb-8 text-center font-mono text-xs uppercase tracking-[0.3em] text-base-content/40">
          the path of every task
        </p>
        <div class="flex flex-wrap items-center justify-center gap-x-2 gap-y-3">
          <span
            :for={{step, i} <- Enum.with_index(@pipeline)}
            class="flex items-center gap-2"
          >
            <span class={[
              "rounded-lg border px-3 py-1.5 font-mono text-xs transition",
              step in ["agent", "publish"] && "border-primary/40 bg-primary/10 text-primary-content",
              step not in ["agent", "publish"] &&
                "border-base-content/10 bg-base-content/[0.03] text-base-content/70"
            ]}>
              {String.replace(step, ":", " ")}
            </span>
            <.icon
              :if={i < length(@pipeline) - 1}
              name="hero-chevron-right"
              class="size-3 text-base-content/25"
            />
          </span>
        </div>
        <p class="mt-8 text-center text-sm text-base-content/50">
          A fail in <span class="text-base-content/80">verify</span>
          triggers a bounded retry; delivery only ever happens through a pull request.
        </p>
      </div>
    </section>
    """
  end

  defp risks_section(assigns) do
    ~H"""
    <section id="security" class="mx-auto max-w-7xl px-6 py-20 lg:px-8">
      <.section_heading
        eyebrow="threat model"
        title="What it defends against"
        subtitle="Every risk maps to a concrete, centrally-controlled mitigation — no trust required in the agent or the repo."
      />
      <div class="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <div
          :for={risk <- @risks}
          class="group relative overflow-hidden rounded-2xl border border-base-content/10 bg-base-content/[0.02] p-6 transition hover:-translate-y-1 hover:border-primary/30 hover:bg-base-content/[0.04]"
        >
          <div class="absolute -right-8 -top-8 size-24 rounded-full bg-primary/10 opacity-0 blur-2xl transition group-hover:opacity-100">
          </div>
          <div class="mb-4 inline-grid size-11 place-items-center rounded-xl border border-base-content/10 bg-base-content/5 text-primary">
            <.icon name={risk.icon} class="size-5" />
          </div>
          <h3 class="mb-2 text-lg font-semibold tracking-tight">{risk.title}</h3>
          <p class="text-sm leading-relaxed text-base-content/60">{risk.detail}</p>
        </div>
      </div>
    </section>
    """
  end

  defp stack_section(assigns) do
    ~H"""
    <section id="stack" class="mx-auto max-w-7xl px-6 py-20 lg:px-8">
      <div class="grid gap-14 lg:grid-cols-[0.9fr_1.1fr]">
        <div class="lg:sticky lg:top-28 lg:self-start">
          <.section_heading
            align="left"
            eyebrow="built on established tooling"
            title="Standing on the shoulders of giants"
            subtitle="fleet is deliberately glue, not a new platform. It composes tools you already run and can inspect."
          />
          <div class="mt-8 rounded-2xl border border-base-content/10 bg-base-content/[0.02] p-6">
            <p class="text-sm leading-relaxed text-base-content/60">
              There is no bespoke container runtime, secret store, or agent protocol.
              Routing is a versioned YAML registry, per-repo behavior is a declarative
              <code class="rounded bg-base-content/5 px-1.5 py-0.5 font-mono text-xs">.fleet/</code>
              contract, and the same
              <code class="rounded bg-base-content/5 px-1.5 py-0.5 font-mono text-xs">fleetctl</code>
              commands run on a laptop and in CI.
            </p>
          </div>
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <div
            :for={item <- @stack}
            class="group rounded-2xl border border-base-content/10 bg-base-content/[0.02] p-6 transition hover:border-base-content/20 hover:bg-base-content/[0.04]"
          >
            <div class="flex items-center justify-between">
              <span class="font-mono text-[10px] uppercase tracking-[0.2em] text-primary/80">
                {item.tag}
              </span>
              <.icon
                name="hero-arrow-up-right"
                class="size-4 text-base-content/25 transition group-hover:text-base-content/60"
              />
            </div>
            <h3 class="mt-4 text-lg font-semibold tracking-tight">{item.name}</h3>
            <p class="mt-2 text-sm leading-relaxed text-base-content/60">{item.detail}</p>
          </div>
        </div>
      </div>
    </section>
    """
  end

  defp concepts_section(assigns) do
    ~H"""
    <section id="concepts" class="mx-auto max-w-7xl px-6 py-20 lg:px-8">
      <.section_heading
        eyebrow="concepts"
        title="Small surface, sharp edges"
        subtitle="A handful of names cover the whole system — routing, contract, dispatcher, backends, and the panel."
      />
      <div class="mt-14 overflow-x-auto rounded-2xl border border-base-content/10">
        <table class="w-full border-collapse text-left text-sm">
          <thead>
            <tr class="bg-base-content/[0.03] text-xs uppercase tracking-[0.15em] text-base-content/40">
              <th class="px-6 py-4 font-medium">Concept</th>
              <th class="px-6 py-4 font-medium">What it is</th>
            </tr>
          </thead>
          <tbody>
            <tr
              :for={concept <- @concepts}
              class="border-t border-base-content/5 transition hover:bg-base-content/[0.02]"
            >
              <td class="whitespace-nowrap px-6 py-4 align-top font-mono text-[13px] text-primary">
                {concept.name}
              </td>
              <td class="px-6 py-4 leading-relaxed text-base-content/60">{concept.detail}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="mt-6 text-sm text-base-content/40">
        <span class="font-mono text-base-content/60">Why a Python core?</span>
        The pure logic lives in the dependency-light <span class="font-mono">fleetctl</span>
        CLI so it is unit-testable and runnable outside Jenkins;
        <span class="font-mono">vars/fleetDispatcher.groovy</span>
        is a thin wrapper for trigger plumbing, node routing and credential binding.
      </p>
    </section>
    """
  end

  attr :dispatcher_code, :string, required: true
  attr :smoke_code, :string, required: true
  attr :panel_code, :string, required: true

  defp quickstart(assigns) do
    ~H"""
    <section id="start" class="mx-auto max-w-7xl px-6 py-20 lg:px-8">
      <.section_heading
        eyebrow="quickstart"
        title="From clone to first PR"
        subtitle="The dispatcher core and the panel run without Jenkins. The webhook → pipeline → PR flow needs a Jenkins you operate yourself."
      />

      <div class="mt-14 grid gap-5 lg:grid-cols-3">
        <.code_card
          label="01 · dispatcher"
          title="Run the bounded loop locally"
          code={@dispatcher_code}
        />
        <.code_card
          label="02 · smoke test"
          title="Real COI container, stub agent"
          code={@smoke_code}
        />
        <.code_card
          label="03 · admin panel"
          title="Phoenix LiveView ledger"
          code={@panel_code}
        />
      </div>

      <div class="mt-10 flex flex-wrap items-center gap-4 rounded-2xl border border-base-content/10 bg-base-content/[0.02] p-6">
        <.icon name="hero-exclamation-triangle" class="size-5 text-warning" />
        <p class="text-sm text-base-content/60">
          <span class="font-semibold text-base-content/80">Dev defaults are not secrets.</span>
          The bundled local Jenkins and panel use placeholder tokens safe only on a throwaway host — replace them before the host is reachable by anyone else.
        </p>
      </div>
    </section>
    """
  end

  defp code_card(assigns) do
    ~H"""
    <div class="flex min-w-0 flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#0b0d17]/80">
      <div class="border-b border-white/5 bg-white/[0.03] px-5 py-4">
        <div class="font-mono text-[10px] uppercase tracking-[0.2em] text-primary/80">{@label}</div>
        <div class="mt-1 text-sm font-semibold text-white/90">{@title}</div>
      </div>
      <div class="min-w-0 flex-1 overflow-x-auto whitespace-pre p-5 font-mono text-xs leading-relaxed text-white/70">
        {@code}
      </div>
    </div>
    """
  end

  defp docs_section(assigns) do
    ~H"""
    <section id="docs" class="mx-auto max-w-7xl px-6 py-20 lg:px-8">
      <.section_heading
        eyebrow="documentation"
        title="Read the fine print"
        subtitle="The contract, the backends, the hardening, and the runbooks — all versioned with the code."
      />
      <div class="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <a
          :for={doc <- @docs}
          href="#docs"
          class="group flex flex-col justify-between rounded-2xl border border-base-content/10 bg-base-content/[0.02] p-5 transition hover:-translate-y-1 hover:border-primary/30 hover:bg-base-content/[0.04]"
        >
          <div class="mb-6 inline-grid size-10 place-items-center rounded-lg border border-base-content/10 bg-base-content/5 text-base-content/60 transition group-hover:text-primary">
            <.icon name="hero-document-text" class="size-5" />
          </div>
          <div>
            <div class="font-mono text-[13px] font-medium text-base-content/90">{doc.name}.md</div>
            <div class="mt-1 text-xs leading-relaxed text-base-content/50">{doc.detail}</div>
          </div>
        </a>
      </div>
    </section>
    """
  end

  defp footer(assigns) do
    ~H"""
    <footer class="border-t border-base-content/5 bg-base-content/[0.03]">
      <div class="mx-auto flex max-w-7xl flex-col items-center justify-between gap-6 px-6 py-12 lg:flex-row lg:px-8">
        <div class="flex items-center gap-3">
          <span class="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-primary to-accent text-primary-content">
            <.icon name="hero-command-line" class="size-4" />
          </span>
          <span class="text-sm text-base-content/50">
            <span class="font-mono text-base-content/80">fleet</span>
            — delegate the typing. Keep the authority.
          </span>
        </div>
        <div class="flex flex-wrap items-center justify-center gap-6 text-sm text-base-content/50">
          <a href="#security" class="transition hover:text-base-content">Security</a>
          <a href="#stack" class="transition hover:text-base-content">Stack</a>
          <a href="#docs" class="transition hover:text-base-content">Docs</a>
          <a href="#" class="transition hover:text-base-content">Contributing</a>
        </div>
      </div>
    </footer>
    """
  end

  attr :eyebrow, :string, required: true
  attr :title, :string, required: true
  attr :subtitle, :string, default: nil
  attr :align, :string, default: "center"

  defp section_heading(assigns) do
    assigns = assign_new(assigns, :align, fn -> "center" end)

    ~H"""
    <div class={["max-w-2xl", @align == "center" && "mx-auto text-center"]}>
      <p class="font-mono text-xs uppercase tracking-[0.3em] text-primary/80">{@eyebrow}</p>
      <h2 class="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">{@title}</h2>
      <p :if={@subtitle} class="mt-4 text-base-content/60">{@subtitle}</p>
    </div>
    """
  end
end
