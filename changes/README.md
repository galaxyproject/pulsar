# Changelog entries

Each pull request adds a file here named `<PR number>.<type>.md`; `make release`
collects them into `CHANGELOG.md` with [towncrier](https://towncrier.readthedocs.io/).

Types:

- `change`: a behavior change or removal that deployers need to know about.
- `feature`: new functionality.
- `bugfix`: a fix.
- `misc`: documentation, testing, packaging, and other changes.

Write one or two sentences of Markdown for someone deploying Pulsar, and credit
outside contributors, e.g. `changes/526.bugfix.md`:

```markdown
Follow redirects in the curl transport (thanks to [@nuwang](https://github.com/nuwang)).
```

`make add-change PR=526 TYPE=bugfix` starts one from the pull request title.
A change spanning PRs can repeat the same text in each PR's file; towncrier
merges them into one entry. Pull requests that need no entry get the
`no changelog` label.
