# Deploy Directory

`deploy/build_fpk.sh` is the supported fnOS package build entry.

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
4. Build the fnOS package with `./deploy/build_fpk.sh <version>`.
5. Review generated package changes only as release artifacts.

The install wizard records source, library root, local recycle directory, port, and an initial API Key. It does not create external media directories; the Web startup readiness check remains the authority for existence, permissions, mount availability, storage capacity, and recycle locality.

Every successful build runs `scripts/validate_fpk.py` against the real archive and writes `build/nas-media-importer.fpk.sha256`. A local pass is not fnOS UAT; test installation and upgrade on the target device before release.

Do not manually patch the generated package workspace to mirror root source.
