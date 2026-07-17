# Project rules

## Secrets

Never commit or push secrets, tokens, API keys, or other sensitive environment
variables to this repository — not in tracked files, not in commit messages,
not in this file. `.env`/`.env.local` are gitignored; keep it that way and
don't add exceptions. Before `git add -A` or any broad staging, review what's
actually staged (`git status`, `git diff --cached`) and double-check file
contents if anything looks like it could hold a credential, even if the
filename looks innocuous.

Local credentials needed for this project (e.g. a GitHub token for pushing)
should be stored outside this repo's working tree — e.g. via `git
credential-store` (`~/.git-credentials`) — never inside the project
directory, even in a gitignored file.

## Commit messages

Do not add a `Co-Authored-By: Claude` (or similar AI attribution) trailer to
commit messages in this repo.
