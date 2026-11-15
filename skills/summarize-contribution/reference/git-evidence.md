# Gathering git evidence

Run from inside the project repo. Establish facts; do not trust recollection.

## 1. Find the user's commit identities

```bash
git log --format='%an|%ae' | sort | uniq -c | sort -rn
```

People commit under more than one name/email over a project's life (work laptop vs. personal, a
changed surname, a corporate email migration). Web-UI merge commits usually carry the forge display
name, not the local one — so the same person appears twice, once as author of commits and once as
merger of PRs.

Cross-check against the configured identity:

```bash
git config user.name; git config user.email
```

If more than one identity plausibly belongs to the user, **ask** rather than guessing. Attributing
someone else's commits is the worst failure mode this document has.

This step earns its place empirically: the first time it was run, it established that a project's
history began a month later than the user remembered. Recollection of when work started is
routinely wrong, and every date in the summary depends on getting this right.

Set the confirmed identities as a pattern for everything below. **Anchor every alternative and
escape the dots** — `--author` is a substring match against the string `Name <email>`, so an
unanchored fragment silently swallows other people:

```bash
# Anchor on the start of the name, or on the email inside its angle brackets.
ME='^Firstname Lastname <\|<first\.last@example\.com>$\|^altname <'
```

Verify the pattern before using it — the count must equal the sum of that person's rows in the
identity table above, and nobody else's:

```bash
git log --author="$ME" --basic-regexp --format='%an <%ae>' | sort | uniq -c
```

**Never add `--regexp-ignore-case`.** It turns a slightly loose pattern into a wrong one: on a real
vault repo, `--author='Caroline'` matched 5 commits while `--author='Caroline' --regexp-ignore-case`
matched 42, silently absorbing a *different* contributor's identity. `\|` alternation under
`--basic-regexp` is safe; unanchored and case-insensitive matching is not.

## 2. True date range

```bash
git log --author="$ME" --basic-regexp --format='%ad' --date=short | sort | sed -n '1p;$p'
```

Report this back if it differs from the range the user claimed. On an update, only the span since the
existing document's last covered date is new — but read the older commits anyway if the existing
document is thin on them.

## 3. Volume and scale

```bash
# commit count (non-merge)
git log --author="$ME" --basic-regexp --no-merges --oneline | wc -l

# insertions / deletions
# Binary files emit "-\t-\tpath"; the numeric guard skips them instead of counting them as 0.
git log --author="$ME" --basic-regexp --no-merges --numstat --format= \
  | awk '$1 ~ /^[0-9]+$/ {a+=$1; d+=$2} $1 == "-" {bin++} \
         END {print "insertions:", a, "deletions:", d, "(binary files skipped:", bin+0")"}'
```

Bound with `--since=YYYY-MM-DD` when updating. State scale as an order of magnitude ("roughly 275
commits across 60+ tickets"); precise counts read as padding, and vendored or generated files distort
line totals — spot-check before quoting them.

## 4. What was worked on

```bash
# authored commits, newest first
git log --author="$ME" --basic-regexp --no-merges \
  --format='%ad %s' --date=short

# files touched most (where the user's centre of gravity was)
git log --author="$ME" --basic-regexp --no-merges --name-only --format= \
  | sort | uniq -c | sort -rn | head -40

# ticket / issue keys
git log --author="$ME" --basic-regexp --format='%s %b' \
  | grep -oE '[A-Z][A-Z0-9]+-[0-9]+' | sort -u

# branch slugs — often describe the work better than the messages.
# Merge subjects ONLY: grepping all subjects harvests ordinary English ("into the", "from plugin").
# Not filtered by author — merge commits are often authored by the forge, not the person.
git log --merges --format='%s' \
  | grep -oE "Merge (branch|pull request [^ ]+ from) '?[^' ]+" \
  | sed -E "s/^Merge (branch|pull request [^ ]+ from) '?//" | sort -u

git branch -a --format='%(refname:short)'
```

## 5. Authored vs. shipped vs. integrated

Three different claims. Keep them apart.

Detect the mainline ref first — hardcoding `main` **fatals** (`unknown revision`) on a repo that
uses `master` or `develop`, aborting the step rather than degrading:

```bash
MAIN=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
[ -n "$MAIN" ] || for b in main master develop trunk; do
  git show-ref --verify --quiet "refs/heads/$b" && MAIN=$b && break
done
echo "mainline: ${MAIN:?could not detect mainline — ask the user}"
```

```bash
# merges into the mainline attributed to the user = PRs/MRs they approved and shipped
git log --merges --author="$ME" --basic-regexp \
  --first-parent "$MAIN" --format='%ad %s' --date=short

# all merges of the user's branches, whoever merged them
git log --merges --format='%an %s' | grep -iE 'feature/|bugfix/|release/'
```

- **Authored** — their non-merge commits. Individual contribution.
- **Shipped** — merge commits into mainline under their identity. Review and release
  responsibility, which is a different and often more senior claim.
- **Integrated** — their own merges of mainline into feature branches. Long-lived-branch labour;
  real work, frequently invisible, and worth naming when it was hard.

## 6. Epics and collaboration

```bash
# epic branches the user's work merged into or against
git log --author="$ME" --basic-regexp --format='%s' \
  | grep -oE 'epic/[^ ]+' | sort -u

# who else worked in the same areas (collaboration evidence)
git log --no-merges --format='%an' -- <path-the-user-touched-most> | sort | uniq -c | sort -rn
```

Record which larger efforts the user participated in **and be explicit that not all work within them
was theirs**. Mark contribution-or-review efforts as such, per effort, in the output.

## 7. Caveats

- Squash-merge repos collapse authorship into one commit per PR; commit counts understate the work
  and `--numstat` overstates individual changes. Note the merge style if it materially affects scale.
- Rebased or force-pushed histories lose original dates. If dates look implausible, say so rather
  than quoting them confidently.
- Pair-programmed commits may carry a `Co-authored-by` trailer:
  ```bash
  git log --format='%b' | grep -i 'co-authored-by' | sort | uniq -c | sort -rn
  ```
  This is collaboration evidence — use it, and don't claim sole authorship where it appears.
- Generated files, lockfiles and vendored directories inflate line counts. Exclude them when quoting
  volume: `-- . ':(exclude)package-lock.json' ':(exclude)vendor/'`.

## 8. Case-study signals

Starting points for the prompts in `Contributions/CaseStudyPrompts.md`. Each is a lead to read, not
a story on its own — open the commit or PR before tagging anything.

```bash
# reverts and hotfixes — owned-mistake, production-incident
git log --author="$ME" --basic-regexp --format='%ad %h %s' --date=short \
  | grep -iE 'revert|hotfix|rollback|roll back'

# reverts of the user's own commits, by whoever reverted them
mine=$(git log --author="$ME" --basic-regexp --no-merges --format=%H)
git log --all --grep='This reverts commit' --format='%x00%ad %h %s %b' --date=short \
  | tr '\n' ' ' | tr '\0' '\n' | grep -F "$mine"

# commits outside working hours (before 08:00, after 20:00, or weekends) — incidents, deadlines
git log --author="$ME" --basic-regexp --no-merges --format='%ad %h %s' \
  --date=format:'%a %H:%M' | awk '$1 ~ /Sat|Sun/ || $2 < "08:00" || $2 > "20:00"'

# AI-assisted commits — ai-tools
git log --author="$ME" --basic-regexp --format='%ad %h %s' --date=short \
  -i --grep='co-authored-by: \(claude\|copilot\|cursor\|codex\|gemini\)'

# root-cause write-ups — detective-bug
git log --author="$ME" --basic-regexp --format='%ad %h %s' --date=short \
  -i --grep='root cause\|race\|flaky\|timezone'

# commit bursts — hard-deadline (days with the most commits)
git log --author="$ME" --basic-regexp --no-merges --format='%ad' --date=short \
  | sort | uniq -c | sort -rn | head -10

# when the user first touched each top-level directory — fast-ramp-up, legacy-migration
git log --author="$ME" --basic-regexp --no-merges --reverse --name-only --format='%ad' --date=short \
  | awk 'NF==1 && /^[0-9-]+$/ {d=$1; next} NF {if (split($0,a,"/") > 1 && !(a[1] in s)) {s[a[1]]=d; print d, a[1]}}'
```

With `gh` (or `glab mr list` equivalents):

```bash
# closed without merging — cancelled-project
gh pr list --author @me --state closed --limit 200 --json number,title,mergedAt,closedAt \
  --jq '.[] | select(.mergedAt == null) | "\(.closedAt[:10]) #\(.number) \(.title)"'

# most-discussed PRs the user authored — technical-disagreement, scope-pushback
gh pr list --author @me --state all --limit 200 --json number,title,comments,reviews \
  --jq 'sort_by(-(.comments|length) - (.reviews|length)) | .[:10][] | "#\(.number) \(.title)"'

# PRs the user reviewed — mentoring, influence-adoption
gh search prs --reviewed-by @me --repo "$(gh repo view --json nameWithOwner --jq .nameWithOwner)" \
  --limit 100 --json number,title,author --jq '.[] | "#\(.number) \(.author.login) \(.title)"'
```

The `Commits: low` prompts — disagreement, scope pushback, mentoring, cancelled work — rarely
surface here at all. Their best source is the `Case study:` lines in the workspace logs, then the
user.
