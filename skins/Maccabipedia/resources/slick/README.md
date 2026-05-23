# Vendored slick-carousel

These files are a byte-identical copy of the slick slider library as served in
production from `https://www.maccabipedia.co.il/customizations/slick/`.

They were previously shipped only by the prod-only `maccabipedia.customizations`
ResourceLoader module (`infra/local-wiki/config/LocalSettings.shared.php`), which
is not present in the repo or the local Docker stack. Vendoring them here makes
the Maccabipedia skin self-contained and lets the slider render/test locally.
See Trello #572.

## Provenance

- Source: `https://www.maccabipedia.co.il/customizations/slick/` (mirrors the layout there:
  `slick-theme.less` references `./ajax-loader.gif` and the `./fonts/` icon webfont via
  LESS path variables, so those assets are vendored alongside it).
- Fetched: 2026-05-23
- The minified JS carries no version banner, so each file is pinned by sha256:

  | File                   | sha256 |
  |------------------------|--------|
  | `slick.min.js`         | `4f183d6af3e88171a4bbae9a2e77f90f55b425b013d057b80eade59f96ae5d0d` |
  | `slick.less`           | `e1baf13cf3333cfc54cdefe7b5ca7a1b4b8f91caf6881375faaec9004fff6d86` |
  | `slick-theme.less`     | `f54b53f3bf102abb179ba7ea4fbd7a187cd07e9eacb1c6d8709224e5782c04b0` |
  | `ajax-loader.gif`      | `4b5ba4b5260c6481c912d1446aeff71d472d8dea7a67debc1582228fe1da51b8` |
  | `fonts/slick.eot`      | `06d80cf01250132fd1068701108453feee68854b750d22c344ffc0de395e1dcb` |
  | `fonts/slick.woff`     | `26726bac4060abb1226e6ceebc1336e84930fe7a7af1b3895a109d067f5b5dcc` |
  | `fonts/slick.ttf`      | `37bc99cfdbbc046193a26396787374d00e7b10d3a758a36045c07bd8886360d2` |
  | `fonts/slick.svg`      | `12459f221a0b787bf1eaebf2e4c48fca2bd9f8493f71256c3043e7a0c7e932f6` |

## Updating

Re-fetch from the source URL and update the checksums above. Do not hand-edit —
the skin's own slider styles (`customize/styles/atoms/images-slider.less`,
`promotions-slider.less`) layer on top of these base styles. Keep the `fonts/`
subdir and `ajax-loader.gif` next to `slick-theme.less`; its relative `url()`
references resolve against that layout.
