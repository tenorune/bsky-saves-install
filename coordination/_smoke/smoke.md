# Coordination workflow dry-run

This file is a throwaway used to verify the `coordination-pr` workflow
end-to-end on the `tenorune/bsky-saves-install` repo:

- The workflow can read the manifest from the `coordination` branch.
- The PAT secret `BSKY_SAVES_COORDINATION_TOKEN` resolves correctly.
- The push to a fresh branch on `tenorune/bsky-saves-coordination`
  succeeds.
- The REST `POST /repos/.../pulls` call opens a PR successfully.

Close the resulting PR on the coord repo without merging. Real
coordination PRs will follow this same path with real content
(starting with the Q8 resolution for the installer-status-panel
contract).

Opened by the installer team's coordination workflow.
