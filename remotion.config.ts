// Remotion CLI config: https://www.remotion.dev/docs/config
import { Config } from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setJpegQuality(92);
Config.setCodec('h264');
Config.setPixelFormat('yuv420p');
Config.setCrf(18); // high quality master; helpers/finish.py makes the <30 MB / -14 LUFS delivery copy
Config.setOverwriteOutput(true);
Config.setConcurrency(null); // auto (half the CPU threads)
