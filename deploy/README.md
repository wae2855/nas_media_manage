# Deploy Directory

`deploy/build_fpk.sh` is the supported fnOS package build entry.

The package downloads platform-independent Python wheels for offline installation. GuessIt is pinned as the general release-name parser, and `server/THIRD_PARTY_NOTICES.md` records its license and transitive dependencies. Upgrades install the pinned `requirements-fnos.lock` into the existing application venv.

`deploy/nas-media-importer/` is a generated package workspace. It is retained in git for now, but application code inside `deploy/nas-media-importer/app/server/media_importer/` is not the source of truth.

Development source of truth:

- `media_importer/`
- `config.yaml.example`
- `requirements.txt`
- `deploy/build_fpk.sh`
- `deploy/icons/`

Release rule:

1. Make application changes in root source.
2. Run the required tests from the repository root.
3. The package declares the official fnOS `python312` dependency and creates its venv under `${TRIM_PKGVAR}`.
4. Run `python scripts/release_ledger.py status`, update the root `VERSION` above the latest candidate, then build with `./deploy/build_fpk.sh`. An optional version argument is only an equality assertion and must match `VERSION`.
5. Review generated package changes only as release artifacts.

The install wizard explains first-run setup. Directory selection and authorization happen in the Web configuration flow; the managed service port and empty service authentication are not user inputs.

Every successful build copies root `VERSION` to `app/server/VERSION`, runs `scripts/validate_fpk.py` against the real archive, verifies the manifest/runtime version match, writes `build/nas-media-importer.fpk.sha256`, and records a candidate in `release-ledger.json`. The gate rejects lower versions and same-version/different-source builds. A local pass is not fnOS UAT; after real-device acceptance, explicitly run `python scripts/release_ledger.py mark-verified --version <version> --note "<acceptance>"`.

Do not manually patch the generated package workspace to mirror root source.
