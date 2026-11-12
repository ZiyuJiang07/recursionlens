# Release procedure

1. Update `CHANGELOG.md`, the package version, and user documentation.
2. Run the full test suite and build a wheel with `python -m pip wheel . --no-deps`.
3. Install the wheel in a fresh environment and run `examples/quickstart.py`.
4. Test the demo notebook in the course DIVE JupyterLab environment.
5. Commit and tag the release only after all checks pass.
6. For a future PyPI release, use a trusted publishing token or OIDC, keep `project.urls.Homepage` pointed at `https://github.com/ZiyuJiang07/recursionlens`, and verify `pip install recursionlens` in another clean environment.
7. Never commit PyPI tokens, GitHub tokens, or other credentials to this repository.
