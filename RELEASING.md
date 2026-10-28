# Releasing

A release is a tag `vX.Y.Z` pushed on `main`. The release workflow does the rest:

1. it checks that the tag matches the package version, `releases.toml` and `CHANGELOG.md`, and
   runs the tests;
2. it builds the wheel and the sdist once, and signs their provenance;
3. it publishes them on [PyPI](https://pypi.org/project/fakeverse/) with trusted publishing and
   PEP 740 attestations, once a maintainer approves the `pypi` environment;
4. it builds the image of the API for `linux/amd64` and `linux/arm64`, with an SBOM and a signed
   provenance, and pushes it to `ghcr.io/kentrow/fakeverse`;
5. it creates the GitHub release, with the notes of `CHANGELOG.md`, the distributions and their
   provenance.

Everything before the tag is about making sure those notes, and what they describe, are right.
Releases are cut by the maintainers; the commands below assume the `gh` CLI is logged in.

## Which number

The [versioning policy](CONTRIBUTING.md#versioning) decides, and `scripts/release.py`
applies it: it reads the Conventional Commits since the last release, and whether the universe
data or `ENGINE_REVISION` changed. The image gets the tags `X.Y.Z`, `X.Y` and `latest`, and from
1.0.0 on `X` too; no `0` tag is published, so that it never moves under anyone.

## 1. Prepare the release branch

Start from an up-to-date `main` on which the CI is green:

```bash
git switch main && git pull --ff-only origin main
uv run python scripts/release.py prepare --dry-run   # the proposed version, and why
git switch -c chore/release-X.Y.Z
uv run python scripts/release.py prepare             # or --version X.Y.Z to override
```

`prepare` dates the `[Unreleased]` section of `CHANGELOG.md` and updates its links, sets
`__version__` and appends the release to `releases.toml`. It refuses to run when the
`[Unreleased]` section is empty, or when `ENGINE_REVISION` changed and the section does not say
so.

## 2. Read the notes the workflow will publish

They become the public release page:

```bash
uv run python scripts/release.py notes X.Y.Z
```

## 3. Run every check

```bash
uv sync --all-extras
uv run pre-commit run --all-files
uv run pytest
uv run fakeverse check-coherence
uv run python scripts/release.py check vX.Y.Z
scripts/check_deployment.sh   # the image behind nginx, with Docker
```

## 4. Merge

```bash
git commit -s -am "chore(release): X.Y.Z"
git push -u origin chore/release-X.Y.Z
gh pr create --base main --title "chore(release): X.Y.Z" --body "Release X.Y.Z."
gh pr checks --watch
gh pr merge --squash --delete-branch
```

## 5. Tag

Nothing else may be merged between the release pull request and the tag, or the notes no longer
describe what is published.

```bash
git switch main && git pull --ff-only origin main
git log --oneline -1          # must be "chore(release): X.Y.Z"
git tag -a vX.Y.Z -m "Fakeverse X.Y.Z"
git push origin vX.Y.Z
gh run watch
```

Approve the `pypi` environment when the workflow asks for it.

## 6. Check what was published

```bash
gh release view vX.Y.Z
uvx --from fakeverse==X.Y.Z fakeverse --version
docker run --rm ghcr.io/kentrow/fakeverse:X.Y.Z fakeverse --version
docker buildx imagetools inspect ghcr.io/kentrow/fakeverse:X.Y.Z
gh attestation verify oci://ghcr.io/kentrow/fakeverse:X.Y.Z --repo Kentrow/fakeverse
gh release download vX.Y.Z --pattern '*.whl' --dir /tmp/fakeverse-X.Y.Z
gh attestation verify /tmp/fakeverse-X.Y.Z/*.whl --repo Kentrow/fakeverse
```

The image index lists both platforms, and its tags share one digest. On PyPI, the files of the
release show their provenance.

## 7. After the release

Close the milestone of the release, so that no new issue is filed under a version that has
shipped:

```bash
gh api "repos/Kentrow/fakeverse/milestones?state=open" --jq '.[] | "\(.number) \(.title)"'
gh api -X PATCH repos/Kentrow/fakeverse/milestones/NUMBER -f state=closed
```

The badges of the README can keep showing the previous version, or no package at all, for a
while: GitHub serves images through its own cache. To refresh them, take the
`camo.githubusercontent.com` addresses of the badges from the repository page and purge them:

```bash
curl -s https://github.com/Kentrow/fakeverse | grep -o 'https://camo.githubusercontent.com/[a-f0-9/]*'
curl -X PURGE "<the address of a badge>"
```

## If a tag went out wrong

Before the release is announced anywhere, and if PyPI did not publish it yet, a tag and its
release can be taken back and cut again:

```bash
gh release delete vX.Y.Z --yes
git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z
```

A version published on PyPI can never be uploaded again, even after a deletion: publish a new
patch version instead, and yank the faulty one on PyPI if it is harmful.
