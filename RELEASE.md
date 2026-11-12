# Release procedure

1. Update `CHANGELOG.md`, the package version, and user documentation.
2. Run the full test suite.
3. Build both distribution archives with `python -m build`.
4. Run `python -m twine check dist/*`.
5. Install the built wheel in a fresh environment and run `examples/quickstart.py`. Confirm `import recursionlens` reports the expected version.
6. Inspect the rendered README links and PyPI metadata before uploading.
7. Commit and tag the release only after all local checks pass.
8. Publish `dist/recursionlens-<version>*` to PyPI using a project-scoped API token or Trusted Publishing. Keep `project.urls.Homepage` pointed at `https://github.com/ZiyuJiang07/recursionlens`.
9. Verify `pip install recursionlens` in another clean environment.
10. Never commit PyPI tokens, GitHub tokens, or other credentials to this repository.

Published files are immutable. If a release is wrong, publish a new patch version; do not rely on deleting and reusing the version number.
