# sample-repo

Demo source repository for the `.fleet` contract. The dispatcher clones this
repo, loads `.fleet/fleet.toml`, renders `.fleet/prompts/task.md`, runs the
agent inside COI, then gates the result with `.fleet/verify.sh`.
