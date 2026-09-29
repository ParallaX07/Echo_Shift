# Echo Shift Sprite Style Bible

## Fixed prompt prefix

`32x32 game sprite, flat chunky pixel art, top-down three-quarter view, orthographic game-camera view, hard-edged pixels, no anti-aliasing, one-pixel dark navy outline, light from top-left, limited PICO-8 palette, centered subject, transparent background, no text, no border, no cast shadow, consistent scale and anchor.`

## Locked rendering rules

- Palette is `assets/palette.json`; index 0 is transparent and must never appear in opaque art.
- Preferred technician design: the young character from `reference/concept.png`, with short tousled brown hair, partly visible face, amber-orange utility jacket, dark work trousers, belt and sturdy boots. Keep the frontal-facing, top-down three-quarter game view.
- Characters are viewed from above at a three-quarter angle, facing toward the bottom of the canvas.
- Character feet share baseline y=29. Leave at least 2 px around the subject.
- Player is an amber technician (index 9) with outline index 1. Echo uses the same silhouette, cyan-blue outline (index 12), and hollow dark interior.
- Light comes from the top-left. Use clear clusters and chunky pixels; no antialiasing or gradients.
- Floor tiles fill the entire 32x32 cell and must repeat without seams.
- Safe areas need both a distinct texture and colour. Do not bake pad/device labels into art.
- Opaque-pixel floors are 64 for characters, 700 for tiles, 24 for props and 16 for icons. The retained nearest-neighbor spike produced 218 opaque character pixels and 784 floor pixels; these limits allow modest silhouette detail and edge variation while rejecting nearly blank assets.

## Do

- Match approved reference sprites in silhouette, proportions, palette and pixel scale.
- Keep every sprite legible at native 32x32 size.
- Use transparent background; use `#FF00FF` only as a fallback for outputs without usable alpha.
- Generate a single centered subject per sprite.

## Do not

- Do not change the approved technician design between frames or assets.
- Do not use index 0 as a visible colour.
- Do not use blur, antialiasing, smooth gradients, perspective projection or drop shadows.
- Do not draw text or letter labels into sprites.
- Do not stretch artwork to fit; preserve aspect ratio.
