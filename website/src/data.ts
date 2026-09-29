export const githubUrl = "https://github.com/wrbl606/fleet";

export const risks = [
  {
    icon: "bolt",
    title: "Prompt injection",
    detail:
      "An issue, PR comment, or repo file weaponizes the agent → it runs in a disposable sandbox with only the task repo mounted. Tokens and host are out of reach, and every change is still a human-reviewed PR.",
  },
  {
    icon: "globe-alt",
    title: "Malicious repo",
    detail:
      "Egress is an allowlist, and COI domains/caps come from the trusted registry — never the repo. Untrusted repos get a hardened profile by default.",
  },
  {
    icon: "arrows-pointing-out",
    title: "Repo widens its own sandbox",
    detail:
      "A repo manifest may request policy but can never exceed central coi caps or the domain allowlist. The gate fails closed.",
  },
  {
    icon: "key",
    title: "Compromised agent",
    detail:
      "The agent gets no GitHub token. A separate trusted publisher stage uses a scoped token to commit and push only to the task branch.",
  },
  {
    icon: "cpu-chip",
    title: "Bare-metal escape",
    detail:
      "Native runs are fail-closed: an OS sandbox (Seatbelt/PF, Windows wrapper) plus explicit repo and node allowlists — or they do not run.",
  },
  {
    icon: "shield-check",
    title: "Forged webhooks",
    detail:
      "Webhooks are token-authenticated. PR-comment triggers are restricted by author association/allowlist and only ever update an existing PR branch.",
  },
  {
    icon: "clock",
    title: "Runaway activity",
    detail:
      "A bounded setup → agent → verify loop with timeouts and registry caps. Every run is recorded in the ledger and ingest log; delivery is only via PR.",
  },
];

export const stack = [
  {
    name: "Jenkins",
    tag: "control plane",
    detail: "Webhook ingress (Generic Webhook Trigger), node routing, and per-run credential binding.",
  },
  {
    name: "Incus + COI",
    tag: "linux sandbox",
    detail: "Containers-on-Incus, plus native Seatbelt/PF and Windows wrappers for allowlisted bare-metal nodes.",
  },
  {
    name: "Git + gh CLI",
    tag: "delivery",
    detail: "Checkout, scoped pushes, and pull requests — with no bespoke VCS layer.",
  },
  {
    name: "Headless agents",
    tag: "the worker",
    detail: "Existing CLI agents (claude, codex, opencode, …), each given only the LLM key it needs.",
  },
  {
    name: "Python fleetctl",
    tag: "dispatcher core",
    detail: "Stdlib-first, dependency-light, unit-testable and runnable outside Jenkins.",
  },
  {
    name: "Phoenix LiveView",
    tag: "admin panel",
    detail: "Run ledger, ingest log, manual trigger, and GitOps config PRs in real time.",
  },
];

export const concepts = [
  {
    name: "registry.yaml",
    detail:
      "Trusted routing and policy: which project maps to which repo, what is allowlisted, and the sandbox caps.",
  },
  {
    name: ".fleet/",
    detail: "The per-repo contract: the prompt, the setup and verify steps, and PR metadata.",
  },
  {
    name: "registry.local.yaml",
    detail: "A git-ignored overlay for deployment-specific routing on top of the tracked registry.",
  },
  {
    name: "fleetctl",
    detail: "The dispatcher core: normalize, resolve, plan, run the bounded loop, publish, notify.",
  },
  {
    name: "Runner backends",
    detail:
      "Sandboxed runners — containers on Linux and native OS controls on macOS/Windows, both fail-closed.",
  },
  {
    name: "PR-comment trigger",
    detail: "Comment on a pull request to iterate on the change; policy decides who may trigger.",
  },
  {
    name: "Admin panel",
    detail: "Run ledger, ingest log, manual trigger, and GitOps config — a Phoenix LiveView app.",
  },
];

const repoDoc = (name: string) =>
  `https://github.com/wrbl606/fleet/blob/main/docs/${name}.md`;

export const docs = [
  { name: "installation", detail: "Host, dispatcher, panel, Jenkins", href: "/docs/installation" },
  { name: "triggers", detail: "Ingest endpoint, forwarding, PM sources", href: "/docs/triggers" },
  { name: "fleet-contract", detail: ".fleet/ contract + templating", href: repoDoc("fleet-contract") },
  { name: "runner-backends", detail: "COI / native backends, routing, secrets", href: repoDoc("runner-backends") },
  { name: "coi-images", detail: "Custom COI images (e.g. the Flutter profile)", href: repoDoc("coi-images") },
  { name: "security", detail: "Trust boundaries, credentials, hardening", href: repoDoc("security") },
  { name: "jenkins-node", detail: "Jenkins controller + build-node requirements", href: repoDoc("jenkins-node") },
  { name: "bare-metal-hardening", detail: "macOS / Windows host hardening", href: repoDoc("bare-metal-hardening") },
  { name: "scale-observability", detail: "Pools, autoscaling, audit shipping, metrics", href: repoDoc("scale-observability") },
];

export const pipeline = [
  "webhook",
  "panel:ingest",
  "jenkins:gwt",
  "normalize",
  "resolve",
  "clone",
  "plan",
  "setup",
  "agent",
  "verify",
  "publish",
];

export type Segment = [cls: string, text: string];

export const terminalLines: Segment[][] = [
  [
    ["text-white/40", "$ "],
    ["text-white/90", "fleetctl run"],
  ],
  [
    ["text-sky-400", "→ normalize"],
    ["", "  task received"],
  ],
  [
    ["text-sky-400", "→ resolve"],
    ["", "    project → repo, from policy"],
  ],
  [
    ["text-sky-400", "→ plan"],
    ["", "       sandbox and caps from the registry"],
  ],
  [
    ["text-emerald-400", "→ setup"],
    ["", "      ready"],
  ],
  [
    ["text-emerald-400", "→ agent"],
    ["", "      working · "],
    ["text-amber-400", "no github token"],
  ],
  [
    ["text-emerald-400", "→ verify"],
    ["", "     passed"],
  ],
  [
    ["text-fuchsia-400", "→ publish"],
    ["", "    pull request opened"],
  ],
  [["text-white/40", "awaiting human review"]],
];

export const setupCode = `git clone https://github.com/wrbl606/fleet.git
cd fleet
python3 -m pip install -r requirements.txt`;

export const coreCode = `python3 -m fleetctl env-check
bash scripts/smoke.sh`;

export const panelCode = `mise install
bash admin/start.sh`;
