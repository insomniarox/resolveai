# Pull Request Workflow

ResolveAI uses a feature-branch pull request workflow:

```text
main → feature branch → commits → push → pull request → CI → merge → deployment
```

`main` represents the deployable version of the project. New work happens on a
separate branch so GitHub Actions can validate it before it reaches `main` and
triggers a Northflank deployment.

## 1. Start from the latest `main`

```bash
git switch main
```

`git switch` changes the branch currently checked out in the working directory.
This command returns to the local `main` branch.

```bash
git pull --ff-only
```

`git pull` downloads changes from GitHub and updates the current branch.
`--ff-only` permits only a simple fast-forward update; it prevents Git from
creating an unexpected merge commit when the local and remote histories differ.

```bash
git switch -c feature/short-description
```

`-c` creates a new branch from the current commit and immediately switches to
it. Replace `short-description` with the work being performed, for example:

```bash
git switch -c feature/phase-7-3-knowledge-ingestion
```

Create one branch per logical feature or fix. Do this before making or committing
changes so `main` remains unchanged.

## 2. Inspect and commit the changes

After editing files, inspect the working tree:

```bash
git status
```

`git status` shows the current branch and lists modified, new, staged, and
untracked files. Use it to confirm that the commit will contain only intended
work.

```bash
git diff
```

`git diff` displays unstaged changes line by line. It is a final review before
selecting files for the commit.

Stage the intended files explicitly:

```bash
git add path/to/file another/file
```

`git add` places the selected changes in Git's staging area. The next commit
contains staged changes only. Explicit paths reduce the chance of committing an
unrelated local file. When every working-tree change intentionally belongs to
the same commit, `git add .` stages everything under the current directory.

Review the staged result:

```bash
git diff --staged
```

`--staged` shows exactly what the next commit will contain.

Create the commit:

```bash
git commit -m "Describe the change"
```

`git commit` records the staged snapshot in the current branch. `-m` supplies a
short commit message. Prefer a specific description such as:

```bash
git commit -m "Add runtime knowledge ingestion"
```

## 3. Push the feature branch

```bash
git push -u origin feature/short-description
```

`git push` sends the branch and its commits to GitHub. `origin` is this
repository's GitHub remote. `-u` records the relationship between the local and
remote branches, so later updates need only `git push`.

The branch is now available on GitHub, but `main` has not changed.

## 4. Open the pull request

On GitHub, open a pull request with:

- base branch: `main`;
- compare branch: the new feature branch;
- a concise title describing the complete change;
- a description covering what changed, why it changed, and how it was tested.

Creating the pull request does not merge the code. It creates a review boundary
and triggers the pull-request GitHub Actions checks.

Wait for the backend and frontend checks to pass. If the pull request is ready,
merge it into `main`. Northflank deploys the new version only after the merged
commit reaches `main`.

## 5. Add more commits to an open pull request

Stay on the same feature branch, make the corrections, and run:

```bash
git status
git add path/to/changed-file
git commit -m "Address review feedback"
git push
```

The first three commands inspect, stage, and commit the follow-up. The shorter
`git push` works because the earlier `-u` configured the upstream branch.
GitHub automatically adds the new commit to the existing pull request and reruns
the relevant CI checks. Do not open another pull request for follow-up changes
that belong to the same feature.

## 6. Synchronize after the pull request is merged

```bash
git switch main
git pull --ff-only
```

These commands return to `main` and download the merged result from GitHub.

```bash
git branch -d feature/short-description
```

`git branch -d` deletes the local feature-branch name after Git confirms its
work was merged. It does not remove the merged commits from `main`.

GitHub normally offers a **Delete branch** button after merging. Alternatively,
delete the remote feature branch from the terminal:

```bash
git push origin --delete feature/short-description
```

This removes the now-unneeded branch name from GitHub. It does not undo the
merged pull request.

## If a commit was accidentally made on local `main`

If the commit has **not** been pushed, preserve it on a feature branch:

```bash
git switch -c feature/short-description
git push -u origin feature/short-description
git branch -f main origin/main
```

The first command creates a feature branch pointing to the accidental commit.
The second publishes that branch. The final command moves only the local `main`
branch name back to GitHub's unchanged `origin/main`. It is safe here because the
commit remains reachable from the feature branch.

Then open the pull request from the feature branch into `main` as usual.

If the commit was already pushed directly to shared `main`, do not rewrite the
remote history casually. Inspect the situation first and decide whether a new
corrective commit or a revert is appropriate.

## VS Code equivalents

The same workflow is available through VS Code's Source Control interface:

1. Switch to `main` using the branch indicator in the status bar.
2. Pull or synchronize `main`.
3. Choose **Create new branch** before starting the feature.
4. Review and stage the intended files in Source Control.
5. Enter a commit message and select **Commit**.
6. Select **Publish Branch** for the first push.
7. Open the pull request on GitHub.

The terminal commands remain useful because they make the current branch and
each Git operation explicit.

## Short version

```bash
# Start new work.
git switch main
git pull --ff-only
git switch -c feature/short-description

# Publish the work.
git status
git add path/to/file
git diff --staged
git commit -m "Describe the change"
git push -u origin feature/short-description

# After the pull request is merged.
git switch main
git pull --ff-only
git branch -d feature/short-description
```
