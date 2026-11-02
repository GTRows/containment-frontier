# Contributing

Anyone can fork this public repository and open a pull request. You do not need collaborator access. Issues and proposals for the campaign are welcome too.

This repository contains the public distribution documentation, release metadata, original presentation assets and validation automation. The internal campaign development source is maintained separately. PRs can change the files present here; report campaign-code, quest or recipe bugs through Issues with reproducible evidence. Public visibility does not grant an open-source license; see [LICENSE.md](LICENSE.md). By submitting a contribution, you permit GTRowsss to review, modify and include it in this project under its existing terms. Submit only material you have permission to contribute.

## Pull requests

1. Fork the repository and create a focused branch from `main`.
2. Use an English title with a prefix: `fix:`, `feat:`, `docs:`, `test:`, `ci:` or `chore:`. An optional scope is allowed, for example `docs(install): clarify Java requirements`.
3. Complete the template's **Summary**, **Validation** and **Gameplay impact** sections. Include actual commands/results; do not claim a game test when you only inspected files.
4. Run Python 3.12 or 3.13 from the repository root:

```text
python -m unittest discover -s tests -v
python tools/validate_publication.py
git diff --check
```

5. Open a PR targeting `main`. Automated checks must pass and the maintainer reviews before merging. First-time fork contributors may need maintainer approval before GitHub starts their workflow.

Keep downloaded mods, JARs, pack ZIPs, player saves, logs, backups, local configuration and credentials out of Git. Redact personal paths and addresses before posting diagnostic excerpts. Do not modify or redistribute third-party artwork or binaries without the necessary permission. Preserve required credits and embedded artwork provenance.

## What CI proves

The public tests validate release metadata, local documentation links, original presentation hashes, dependency/world locks, archive integrity and PR format. Fork PR jobs use read-only permissions, no secrets and hosted runners. These jobs do not compile the private campaign module or run Minecraft. Java domain tests and native playtesting are recorded separately in release notes. Successful publication checks do not qualify a full solo/cooperative campaign.

Maintainers can verify a downloaded release with `python tools/validate_publication.py --archive /path/to/pack.zip`, or verify the current public download with `--download`. A published-release workflow performs that download/hash/payload check automatically. Ordinary PR checks work offline and do not download Minecraft dependencies.
