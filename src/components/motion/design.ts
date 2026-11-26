import { useVideoConfig } from 'remotion';

/** Talking-head motion effects are laid out on a 1080x1920 design frame; this scales design px to the real frame. */
export const useDesign = () => {
  const { width, height } = useVideoConfig();
  const ky = height / 1920;
  const kx = width / 1080;
  return { width, height, ky, kx, k: Math.min(kx, ky) };
};

/** Default y (design px) of the progress bar and the centre of the top-band graphic slot (banner / count-up / chip). */
export const BAR_Y = 226;
export const SLOT_Y = 324;
