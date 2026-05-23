# Vendored slick-carousel

These files are a byte-identical copy of the slick slider library as served in
production from `https://www.maccabipedia.co.il/customizations/slick/`.

They were previously shipped only by the prod-only `maccabipedia.customizations`
ResourceLoader module (`infra/local-wiki/config/LocalSettings.shared.php`), which
is not present in the repo or the local Docker stack. Vendoring them here makes
the Maccabipedia skin self-contained and lets the slider render/test locally.
See Trello #572.

## Provenance

- Source: `https://www.maccabipedia.co.il/customizations/slick/{slick.min.js,slick.less,slick-theme.less}`
- Fetched: 2026-05-23
- The minified JS carries no version banner, so the copy is pinned by sha256:

  | File              | sha256 |
  |-------------------|--------|
  | `slick.min.js`    | `4f183d6af3e88171a4bbae9a2e77f90f55b425b013d057b80eade59f96ae5d0d` |
  | `slick.less`      | `e1baf13cf3333cfc54cdefe7b5ca7a1b4b8f91caf6881375faaec9004fff6d86` |
  | `slick-theme.less`| `f54b53f3bf102abb179ba7ea4fbd7a187cd07e9eacb1c6d8709224e5782c04b0` |

## Updating

Re-fetch from the source URL and update the checksums above. Do not hand-edit —
the skin's own slider styles (`customize/styles/atoms/images-slider.less`,
`promotions-slider.less`) layer on top of these base styles.
