@Library('fleet-config@main') _

// fLEET dispatcher job.
//
// The Generic Webhook Trigger receives PM-tool events at:
//   https://<jenkins>/generic-webhook-trigger/invoke?token=<fleet-webhook-token>
// and feeds the pipeline. Configure a Jenkins string credential named
// `fleet-webhook-token` (or change tokenCredentialId below).
// Serialize runs: a second webhook while a run is active must not share the
// workspace or race the same PR branch. (Per-branch locking is a future add.)
options {
  disableConcurrentBuilds(abortPrevious: false)
}

properties([
  pipelineTriggers([
    [
      $class: 'GenericTrigger',
      genericVariables: [
        [key: 'payload', value: '$', expressionType: 'JSONPath']
      ],
      genericRequestVariables: [
        [key: 'source', regexpFilter: '']
      ],
      genericHeaderVariables: [
        [key: 'x-fleet-event', regexpFilter: ''],
        [key: 'x-github-event', regexpFilter: ''],
        [key: 'x-github-delivery', regexpFilter: '']
      ],
      tokenCredentialId: 'fleet-webhook-token',
      causeString: 'Fleet webhook ($source)',
      printContributedVariables: true,
      printPostContent: false,
      silentResponse: false
    ]
  ])
])

fleetDispatcher()
