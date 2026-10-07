# Security policy

Fakeverse generates fake data and serves it through a public API. Security reports are welcome
and taken seriously.

## Supported versions

Security fixes are made on the latest release only, published on PyPI and as a Docker image.
Upgrade to it before reporting, and mention the version you run (`fakeverse --version`, or
`package_version` in `GET /v1/meta`).

## Reporting a vulnerability

Report vulnerabilities **privately**, through GitHub's private vulnerability reporting:

<https://github.com/Kentrow/fakeverse/security/advisories/new>

Never open a public issue, discussion or pull request for a vulnerability. A useful report
includes the version, how Fakeverse runs (package, image, API behind a proxy...), the steps to
reproduce, and the impact you expect.

## What to expect

Fakeverse is maintained in the maintainers' own time.

- An acknowledgment within 72 hours.
- An assessment, and a fix or a mitigation plan, as soon as the issue is understood, typically
  within 30 days.
- A GitHub security advisory published with the fix. Reporters are credited unless they ask
  not to be.

## Scope

In scope: the code of this repository, the package published on PyPI, the image published at
`ghcr.io/kentrow/fakeverse` with its documented configuration, and the universe files.
Examples: a request that makes the API crash or use excessive resources despite its limits, a
way around the rate limit, a universe file that runs code or exhausts memory when loaded.

Out of scope:

- Deployments that ignore the [deployment guide](docs/deployment.md), for instance trusting
  `X-Forwarded-For` from any client, or exposing `/metrics` publicly.
- The content of generated data: it is fake by design. Requests from rights holders follow
  the [takedown procedure](TAKEDOWN.md).

## Verifying what you run

Every release is built by GitHub Actions from a tag, and its distributions and image carry a
signed provenance. See [RELEASING.md](RELEASING.md#6-check-what-was-published) for the
commands that verify them.
