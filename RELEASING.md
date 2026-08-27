# Releasing `astro-colibri`

Production releases are published from GitHub Releases to PyPI through
Trusted Publishing. GitHub supplies a short-lived OpenID Connect identity to
PyPI, so no long-lived PyPI API token is stored in the repository.

The workflow publishes both normal and pre-releases. Publishing a GitHub
Release is therefore the final, irreversible release action.

The GitHub repository may remain private. The wheel, source distribution, and
their packaged source code become public when they are uploaded to PyPI.

## One-time setup

Complete these steps only when the first PyPI publication is ready.

1. Create a PyPI account, verify its email address, enable two-factor
   authentication, and store the recovery codes securely.
2. Confirm that GitHub Actions are enabled for the private
   `astro-transients/astro-colibri` repository. If the organization restricts
   third-party actions, allow `pypa/gh-action-pypi-publish`.
3. In the GitHub repository, open **Settings > Environments**, create an
   environment named `pypi`, and add required reviewers if the GitHub plan
   supports them.
4. Confirm that `.github/workflows/release.yml` is present on the GitHub
   repository's default branch.
5. Sign in to PyPI and open **Your account > Publishing > Add a new pending
   publisher > GitHub**. Enter:

   | Field | Value |
   |---|---|
   | PyPI project name | `astro-colibri` |
   | GitHub owner | `astro-transients` |
   | GitHub repository | `astro-colibri` |
   | Workflow filename | `release.yml` |
   | Environment name | `pypi` |

6. Add the pending publisher. It becomes a normal publisher after the first
   successful upload.

A pending publisher does not reserve the PyPI name. The first successful
production upload creates the PyPI project and reserves `astro-colibri`.
TestPyPI has a separate project namespace and does not reserve the production
name.

## Prepare a release

1. Choose a PEP 440 version. Use an alpha version such as `0.1.0a1` until the
   first stable release is ready.
2. Set exactly the same version in:
   - `pyproject.toml`, under `project.version`.
   - `astrocolibri/_version.py`, as `__version__`.
   - `CITATION.cff`, under `version`.

   The release workflow rejects the release if these three disagree. For a
   stable release, also set `date-released` in `CITATION.cff` to the release
   date in `YYYY-MM-DD` form.
3. Run the local checks from `Colibri_v2/colibri_client`:

   ```bash
   python -m pip install -e ".[dev]"
   python -m pytest
   python -m build
   python -m twine check dist/*
   ```

4. Commit the release changes to the authoritative Astro-COLIBRI GitLab
   branch, merge as appropriate, and synchronize the SDK to GitHub using the
   monorepo's `Colibri_v2/colibri_client/publish_to_github.sh` script.
5. Confirm that the intended commit is present on the GitHub `main` branch and
   that the repository has no unexpected GitHub-only changes.

## Publish a release

1. In GitHub, open **Releases > Draft a new release**.
2. Create a tag named `v<version>`, for example `v0.1.0a1`, targeting the
   intended commit on `main`.
3. Use the same version in the release title and describe the user-visible
   changes.
4. Mark alpha, beta, or release-candidate versions as pre-releases.
5. Review the tag, target commit, and release notes. Keep the release as a
   draft until the one-time PyPI setup is complete.
6. Publish the GitHub Release.

Publishing triggers `.github/workflows/release.yml`. The workflow:

1. Checks out the release tag.
2. Requires the tag to equal `v` plus the version in `pyproject.toml`.
3. Requires `astrocolibri/_version.py` and `CITATION.cff` to contain the same
   version.
4. Installs the package and development dependencies, then runs the tests.
5. Builds and validates the source distribution and wheel.
6. Passes those exact artifacts to a separate job that publishes them to PyPI
   using the `pypi` GitHub environment and Trusted Publishing.

After publishing, verify:

```bash
python -m pip install --upgrade astro-colibri==<version>
python -c "import astrocolibri; print(astrocolibri.__version__)"
```

Also check the PyPI project page, the GitHub Actions run, and the GitHub
Release tag and notes.

## Failure handling

- If validation, tests, or building fail before publication, fix the problem,
  synchronize the corrected commit to GitHub, move or recreate the release tag
  only if it has not been published to PyPI, and rerun the workflow.
- If any file for the version reached PyPI, do not reuse that version. PyPI
  does not permit replacing an uploaded filename. Increment the version and
  create a new GitHub Release.
- If Trusted Publishing fails, verify that the owner, repository, workflow
  filename, and environment on PyPI exactly match the values above.
- Do not add a PyPI API token as a GitHub secret. The publish job requires only
  `id-token: write` permission.
