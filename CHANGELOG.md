# Changelog

## [0.5.0](https://github.com/georg-pitterle/ScoreCap/compare/v0.4.0...v0.5.0) (2026-09-18)


### Features

* adjust a crop by its corners and edges ([78f1947](https://github.com/georg-pitterle/ScoreCap/commit/78f194737bb606a7ea901f48a3ee5c4cfd86d316))
* decide black and white for scans at export ([ae4d25e](https://github.com/georg-pitterle/ScoreCap/commit/ae4d25e5498bb77b47797fd3ecc7c25a3d7f7c2e))
* end systems flush and let trailing marks hang into the margin ([131501d](https://github.com/georg-pitterle/ScoreCap/commit/131501de0812ed35b4a9fbfcf76034ae2bee2d16))
* import scans and split them into systems ([1765bf0](https://github.com/georg-pitterle/ScoreCap/commit/1765bf0fe61e2b64361bd60a90d8a30b0ec2c578))
* offer the interface in German and English ([59b90ae](https://github.com/georg-pitterle/ScoreCap/commit/59b90ae996e119bf7c21013081ee8962c559151d))
* open the crop dialog by double-clicking a capture ([5ebe908](https://github.com/georg-pitterle/ScoreCap/commit/5ebe9080957ee5f5b7ef678879f188f20240ec89))
* remember the last folder of each file dialog ([163428f](https://github.com/georg-pitterle/ScoreCap/commit/163428ffc25e492cb302284a27998b0d2ff28846))
* save and open captures as .scorecap projects ([5216d00](https://github.com/georg-pitterle/ScoreCap/commit/5216d00f5ee2c823ac8ec7b0a15291403d348e83))
* shrink existing PDFs from the toolbar ([6599cf2](https://github.com/georg-pitterle/ScoreCap/commit/6599cf22ef4eac4cece1f91268fe94993846eac4))
* start staff lines flush at the left margin ([19bab33](https://github.com/georg-pitterle/ScoreCap/commit/19bab33bd8fb6a8bd1ccfc1b1997aa65a1739457))


### Bug Fixes

* compress the images in exported PDFs ([0941f48](https://github.com/georg-pitterle/ScoreCap/commit/0941f4823d2e9cf3eb14c1bafa268371fd055b0c))
* keep scanned systems together and crop them tightly ([09f37c1](https://github.com/georg-pitterle/ScoreCap/commit/09f37c1d79f2fc61464680cebb753662e7dfc170))

## [0.4.0](https://github.com/georg-pitterle/ScoreCap/compare/v0.3.0...v0.4.0) (2026-09-12)


### Features

* download updates quietly and install them when the app closes ([b7fc670](https://github.com/georg-pitterle/ScoreCap/commit/b7fc67031295c4fba7c1793c2817e68c7008a4db))
* log start-up and update diagnostics to a file ([59ce9e3](https://github.com/georg-pitterle/ScoreCap/commit/59ce9e37c865d840224dcaacec1d052054df7611))


### Bug Fixes

* stop the preview re-rendering on every step of a window resize ([23ab86a](https://github.com/georg-pitterle/ScoreCap/commit/23ab86ab544dd1e96e477a637fa0ba48d91a85f3))

## [0.3.0](https://github.com/georg-pitterle/ScoreCap/compare/v0.2.1...v0.3.0) (2026-09-12)


### Features

* report the Velopack installation state from the self-test ([f54b83a](https://github.com/georg-pitterle/ScoreCap/commit/f54b83abd3c0d5d403e28533213ed14d5e537546))

## [0.2.1](https://github.com/georg-pitterle/ScoreCap/compare/v0.2.0...v0.2.1) (2026-09-11)


### Bug Fixes

* key the CI skip on the pull request author, not the branch name ([b716dd7](https://github.com/georg-pitterle/ScoreCap/commit/b716dd74832526bb4094b5548b6da24c09f3f280))
* make the bundle self-test survive its own build step ([c702385](https://github.com/georg-pitterle/ScoreCap/commit/c70238598467e3573c27d0769dbac975514688ee))

## [0.2.0](https://github.com/georg-pitterle/ScoreCap/compare/v0.1.0...v0.2.0) (2026-09-11)


### Features

* add A4 pagination engine ([ffb4361](https://github.com/georg-pitterle/ScoreCap/commit/ffb43615e6aceca2b3f2c29082a1d39a29e88cd1))
* add global hotkey, selection overlay and screen grab ([7b1e17e](https://github.com/georg-pitterle/ScoreCap/commit/7b1e17e57ece21cccfbd030dc8624872268783f5))
* add non-destructive crop dialog ([1cf2c83](https://github.com/georg-pitterle/ScoreCap/commit/1cf2c83883d92e5722e2e9abb95c0db92e5a968d))
* add project scaffold and page settings ([4f87331](https://github.com/georg-pitterle/ScoreCap/commit/4f87331b37099f9e28ec70513e9d595c6dafd916))
* add settings dialog with persistence ([9ac164f](https://github.com/georg-pitterle/ScoreCap/commit/9ac164f3dae83c4a444cbbec0474caf5d211c495))
* add shot and document model with undo ([e387c10](https://github.com/georg-pitterle/ScoreCap/commit/e387c10ba5073beffa19f32ec07283bb7cae4e97))
* rebuild the interface around the printed page ([c8d6b5d](https://github.com/georg-pitterle/ScoreCap/commit/c8d6b5d2a5d537c3ea614295064b9f1351b2709f))
* render layout to PDF with page footer ([a5fc952](https://github.com/georg-pitterle/ScoreCap/commit/a5fc9528b72df7de633cb18970ff15d436914266))
* render PDF pages into the preview pane ([7df63e2](https://github.com/georg-pitterle/ScoreCap/commit/7df63e2e6d4c92fc46b30201709c7cfc2eb3ff3d))
* ship a Windows bundle built with PyInstaller ([0b7ee26](https://github.com/georg-pitterle/ScoreCap/commit/0b7ee2654dd76b74e3ded28bad7b58f0ef07bad7))
* trim the white margin off new captures ([357b224](https://github.com/georg-pitterle/ScoreCap/commit/357b224ea8de0337316132fd135d9c62bf807dba))
* update the app from its own GitHub releases ([7b2db4c](https://github.com/georg-pitterle/ScoreCap/commit/7b2db4cb0826e087641c2350379fb88cf070ecfb))
* wire capture, layout, preview and export into the main window ([1e77784](https://github.com/georg-pitterle/ScoreCap/commit/1e77784036568288d59dca320c5426bcbae4ba3b))


### Bug Fixes

* keep the window out of the way during a capture series ([c66cdf9](https://github.com/georg-pitterle/ScoreCap/commit/c66cdf97289623ac20678529fa1eb72e7336dc44))
* let the buttons arm a capture instead of starting one ([0ff9f3b](https://github.com/georg-pitterle/ScoreCap/commit/0ff9f3bb97d6c183baed4493aa24465bef059e01))
* stop the preview chasing its own scrollbar ([435f8ac](https://github.com/georg-pitterle/ScoreCap/commit/435f8ac66e058e76e123f117a3efa056feec08e8))


### Documentation

* add readme and manual acceptance test ([a9e431b](https://github.com/georg-pitterle/ScoreCap/commit/a9e431bf33fc54deb115f1c60f041399784762af))
* add ScoreCap design spec ([bc8f87e](https://github.com/georg-pitterle/ScoreCap/commit/bc8f87e889ea6625bfa27e53533376ee5d0a3ed6))
* add ScoreCap implementation plan ([144e914](https://github.com/georg-pitterle/ScoreCap/commit/144e914f28f36998f6bf006b01765b0fbe479e66))
* match the renamed crop reset button ([5f83091](https://github.com/georg-pitterle/ScoreCap/commit/5f8309103c82c029a527d1a0e6063749de542cc7))
* note the repository setting release-please needs ([b1a4122](https://github.com/georg-pitterle/ScoreCap/commit/b1a4122dfe269f73bcb8e0bf72b41b466cbc35dc))
