# Liquid background poster

`liquid-backdrop-poster.jpg` is the first decoded frame of the background video
already used by `LiquidBackdrop.tsx`, exported at 1600px width as a 53KB JPEG.
It is not new artwork, market data or an account-derived image. It has the same
usage-rights requirements as the existing source video; this change makes no
new licensing claim.

The HTML preloads the local image and Vite fingerprints it in the build. Both
the permanent fallback image and the video poster use this asset. The video
replaces it only after playback begins; network failure, autoplay rejection
and reduced-motion preference therefore do not remove the visual background.
