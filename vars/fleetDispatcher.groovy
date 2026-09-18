// fleetDispatcher — Jenkins shared library entrypoint (P1/P2/P3).
//
// Thin orchestration around the `fleetctl` CLI. Responsibilities that are
// genuinely Jenkins-specific live here:
//   * Generic Webhook Trigger variable plumbing
//   * dynamic node routing via the registry-derived Jenkins label
//   * per-run credential binding (LLM key + scoped GitHub token)
// Everything else (normalize, resolve, plan, COI config, bounded loop,
// publish, notify) is `fleetctl`, so it is identical locally and in CI.
//
// Usage (Jenkinsfile):
//   @Library('fleet-config@main') _
//   fleetDispatcher()
//
// Expected Generic Webhook Trigger contributed variables:
//   payload        raw JSON body (JSONPath '$')
//   source         request param `source` (jira|linear|github), defaults jira
//   x_fleet_event  optional header x-fleet-event

// JSON parsing must happen in a @NonCPS helper: JsonSlurper/JsonSlurperClassic
// instances are not serializable, so creating one inline captures it across a
// CPS suspension point (readFile/sh) and breaks program persistence.
import com.cloudbees.groovy.cps.NonCPS
import groovy.json.JsonSlurperClassic

def call(Map cfg = [:]) {
  def registryPath = cfg.registryPath ?: 'registry.yaml'
  String payload = env.FLEET_PAYLOAD ?: env.payload
  if (!payload) {
    error('fleet: no webhook payload (expected GWT variable "payload")')
  }
  String ghEvent = (env.x_github_event ?: env['x-github-event'] ?: '').trim()
  String source = resolveSource(cfg, ghEvent)
  // For GitHub the actionable event name is the X-GitHub-Event value.
  String event = (source == 'github' && ghEvent)
    ? ghEvent
    : (env.x_fleet_event ?: env['x-fleet-event'] ?: env.FLEET_EVENT ?: '').trim()
  String dispatcherNode = cfg.dispatcherNode ?: 'built-in'
  String readCred = cfg.readTokenCredentialId ?: 'fleet-github-read'

  boolean actionable = false
  Map plan = null
  Map issue = null

  stage('Normalize') {
    node(dispatcherNode) {
      checkout scm
      withEnv(["PYTHONPATH=${env.WORKSPACE}"]) {
        bootstrapPython()
        writeFile file: 'payload.json', text: payload
        def cmd = "python3 -m fleetctl normalize --source ${source} " +
          "--payload-file payload.json --event '${event}' --registry ${registryPath}"
        def raw
        if (source == 'github') {
          // Bind the read token so issue_comment PR metadata can be fetched.
          withCredentials([string(credentialsId: readCred, variable: 'GH_TOKEN')]) {
            raw = sh(script: cmd, returnStdout: true).trim()
          }
        } else {
          raw = sh(script: cmd, returnStdout: true).trim()
        }
        def norm = parseJson(raw)
        if (norm.actionable) {
          actionable = true
          issue = norm.issue
          writeJSON file: 'issue.json', json: issue
          stash includes: 'issue.json', name: 'fleet-issue'
        } else {
          echo "fleet: ${source} event '${event}' is not actionable; nothing to do"
        }
      }
    }
  }

  if (!actionable) {
    currentBuild.result = 'SUCCESS'
    return
  }

  stage('Resolve') {
    node(dispatcherNode) {
      checkout scm
      withEnv(["PYTHONPATH=${env.WORKSPACE}"]) {
        bootstrapPython()
        unstashOrSkip('fleet-issue')
        if (!fileExists('issue.json')) {
          writeJSON file: 'issue.json', json: issue
        }
        def raw = sh(
          script: "python3 -m fleetctl resolve --registry ${registryPath} --issue-file issue.json",
          returnStdout: true
        ).trim()
        plan = parseJson(raw)
        echo "fleet: resolved ${issue.key} -> ${plan.repo} (${plan.jenkins_label})"
      }
    }
  }

  if (plan == null) {
    error('fleet: registry did not resolve a repo for this issue')
  }

  stage('Run') {
    node(plan.jenkins_label) {
      checkout scm
      withEnv(["PYTHONPATH=${env.WORKSPACE}"]) {
        bootstrapPython()
        unstash 'fleet-issue'

        withEnv([
          "FLEET_REPO=${plan.repo}",
          "FLEET_BASE=${plan.base_branch}",
        ]) {
          cloneRepo(cfg)
        }

        // Build the plan on the worker (manifest comes from the cloned repo).
        def planCmd = "python3 -m fleetctl plan --registry ${registryPath} " +
          "--repo-dir target --issue-file issue.json --out plan.json"
        if (source == 'github') {
          withCredentials([string(credentialsId: readCred, variable: 'GH_TOKEN')]) {
            sh planCmd
          }
        } else {
          sh planCmd
        }
        // Parse with JsonSlurperClassic (plain HashMaps / real nulls) rather than
        // readJSON, whose net.sf.json JSONNull breaks withCredentials bindings.
        def workerPlan = parseJson(readFile('plan.json'))

        // PR-comment runs operate on the PR's existing head branch.
        def headBranch = workerPlan.head_branch
        def headRepo = workerPlan.issue?.pr_head_repo
        def sameRepo = !headRepo || headRepo == plan.repo
        if (headBranch && sameRepo &&
            (workerPlan.mode == 'auto' || workerPlan.mode == 'update_pr')) {
          withEnv(["FLEET_HEAD=${headBranch}"]) {
            sh '''
              set -e
              cd target
              git fetch --depth 1 origin "$FLEET_HEAD"
              git checkout -B "$FLEET_HEAD" FETCH_HEAD
            '''
          }
        }

        def llmEnv = workerPlan.manifest.agent.llm_env
        def llmCred = workerPlan.manifest.agent.llm_credential_id ?: llmEnv
        def publishCred = cfg.publishCredentialId ?: 'fleet-github-token'
        def coiConfigDir = "${env.WORKSPACE}/.fleet-coi"
        // FLEET_DRY_RUN=1 makes publish a no-op (local testing without GitHub creds).
        def dryRunFlag = (env.FLEET_DRY_RUN in ['1', 'true', 'yes']) ? '--dry-run' : ''

        def runBlock = {
          withCredentials([string(credentialsId: publishCred, variable: 'GH_TOKEN')]) {
            sh """
              python3 -m fleetctl run \
                --plan-file plan.json \
                --workspace target \
                --coi-config-dir ${coiConfigDir} \
                --registry ${registryPath} \
                --out result.json ${dryRunFlag}
            """
          }
        }

        if (llmEnv && llmCred) {
          withCredentials([string(credentialsId: llmCred, variable: llmEnv)]) {
            runBlock()
          }
        } else {
          runBlock()
        }

        archiveArtifacts artifacts: 'result.json,plan.json', allowEmptyArchive: true
        reportResult()
      }
    }
  }
}

def resolveSource(Map cfg, String ghEvent) {
  def explicit = (env.source ?: '').trim()
  if (explicit) return explicit
  // GitHub webhooks carry no `source` query param; infer from the event header.
  if (ghEvent in ['issues', 'issue_comment', 'pull_request_review_comment', 'pull_request']) {
    return 'github'
  }
  return (cfg.defaultSource ?: 'jira').trim()
}

def bootstrapPython() {
  sh '''
    set -e
    if ! python3 -c "import yaml, jsonschema" >/dev/null 2>&1; then
      python3 -m pip install --user --quiet -r requirements.txt
    fi
  '''
}

def cloneRepo(Map cfg) {
  def base = env.FLEET_GIT_BASE_URL ?: 'https://github.com'
  def remote = "${base}/${env.FLEET_REPO}.git"
  def readCred = cfg.readTokenCredentialId ?: 'fleet-github-read'

  // Single-quoted shell so ${GH_READ_TOKEN} is expanded by the shell, not Groovy.
  def body = '''
    set -e
    rm -rf target
    url="$FLEET_REMOTE"
    case "$url" in
      https://*) url="https://x-access-token:${GH_READ_TOKEN}@${url#https://}" ;;
    esac
    git clone --depth 1 --branch "$FLEET_BASE" "$url" target
  '''

  if (remote.startsWith('http')) {
    withCredentials([string(credentialsId: readCred, variable: 'GH_READ_TOKEN')]) {
      withEnv(["FLEET_REMOTE=${remote}"]) { sh body }
    }
  } else {
    // Local/file remotes (dev) need no credentials.
    withEnv(["FLEET_REMOTE=${remote}"]) { sh body }
  }
}

def unstashOrSkip(String name) {
  try {
    unstash name
  } catch (ignored) {
    // first stage may not have stashed yet
  }
}

def reportResult() {
  def result = parseJson(readFile('result.json'))
  echo "fleet: run ${result.status} (${result.repo} @ ${result.branch}) pr=${result.pr_url}"
  if (result.status == 'failed' || result.status == 'verify_failed') {
    currentBuild.result = 'FAILURE'
  } else {
    currentBuild.result = 'SUCCESS'
  }
}

@NonCPS
def parseJson(String text) {
  new JsonSlurperClassic().parseText(text)
}
