# Takedown procedure

Fakeverse is an independent, non-commercial open source project. Its universe files contain
only short names and labels, but we take requests from rights holders seriously. Each
universe lives in a single file and can be withdrawn from the public API immediately.

## How to make a request

Open a [private security advisory](https://github.com/Kentrow/fakeverse/security/advisories/new)
on the GitHub repository of Fakeverse ("Security" tab, then "Report a vulnerability"). Only the
maintainers can read it.

Please include:

- the universe concerned and, if applicable, the specific names;
- the rights you hold or represent;
- what you ask for (removal of names, of the whole universe, of published versions).

## What happens next

1. **Acknowledgment within 72 hours.**
2. **Immediate removal from the public API**, without a rebuild: the universe is added to the
   `FAKEVERSE_DISABLED_UNIVERSES` setting of the deployment. It then answers
   `universe-not-found` and disappears from every listing.
3. **Removal of the universe file** from the repository, and a new release, **within 7 days**.
4. If you ask for it, versions already published on PyPI are **yanked**.

We will keep you informed in the advisory at each step.
