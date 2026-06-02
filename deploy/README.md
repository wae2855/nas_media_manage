# Deploy Directory

`deploy/build_fpk.sh` is the supported fnOS package build entry.

`deploy/nas-media-importer/` is a generated package workspace. It is retained in git for now, but application code inside `deploy/nas-media-importer/app/server/media_importer/` is not the source of truth.

Development source of truth:

- `media_importer/`
- `hermes/`
- `config.yaml.example`
- `requirements.txt`
- `deploy/build_fpk.sh`
- `deploy/icons/`

Release rule:

1. Make application changes in root source.
2. Run the required tests from the repository root.
3. Build the fnOS package with `./deploy/build_fpk.sh <version>`.
4. Review generated package changes only as release artifacts.

Do not manually patch the generated package workspace to mirror root source.
