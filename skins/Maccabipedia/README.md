# Maccabipedia skin

Modern `SkinMustache`-based skin for MaccabiPedia. Vendored under `skins/Maccabipedia/` and tracked in this repo (no upstream — this is a from-scratch MaccabiPedia skin, not a fork).

## Status

This is the **default skin** (`$wgDefaultSkin = "Maccabipedia"`) on both the local Docker stack and production.

See `docs/superpowers/specs/2026-04-25-maccabipedia-skin-rewrite.md` for the full design.

## Local development

The skin is the default in the local Docker stack, so any page renders with it out of the box:

```bash
cd infra/local-wiki && docker compose up -d
# Then visit http://localhost:8080/עמוד_ראשי
```

## License

GPL-2.0-or-later (see `COPYING`).
