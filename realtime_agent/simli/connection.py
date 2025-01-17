import asyncio
import logging
import os
import av
import io
from pydub import AudioSegment
from simli import SimliClient, SimliConfig

from ..logger import setup_logger

logger = setup_logger(name=__name__, log_level=logging.INFO)


class SimliConnection:
    def __init__(
        self,
        api_key: str | None = None,
        face_id: str = "tmp9i8bbq7c",
    ):
        self.api_key = api_key or os.environ.get("SIMLI_API_KEY")
        self.client = SimliClient(
            SimliConfig(
                apiKey=api_key,
                faceId=face_id,
                syncAudio=True,
                maxSessionLength=60,
                maxIdleTime=30,
            )
        )
        self.write_avatar_video = os.getenv('WRITE_AVATAR_VIDEO', 'false') == 'true'
        if self.write_avatar_video:
            self.container = av.open("output.mp4", "w")
            self.video_stream = self.container.add_stream("mpeg4", width=512, height=512)
            self.audio_stream = self.container.add_stream("aac", rate=48000)
        
        
    async def connect(self):
        await self.client.Initialize()

    async def close(self):
        await self.client.stop()
        if self.write_avatar_video:
            for packet in [self.video_stream.encode(), self.audio_stream.encode()]:
                self.container.mux(packet)
            self.container.close()

    async def send_audio(self, audio: bytes):
        # Downsample to 16Khz. audio is apparently 24Khz according to https://platform.openai.com/docs/api-reference/realtime-sessions/create#realtime-sessions-create-output_audio_format
        current_audio = AudioSegment.from_raw(io.BytesIO(audio), frame_rate=24000, sample_width=2, channels=1)
        resampled_audio = current_audio.set_frame_rate(16000)
        await self.client.send(resampled_audio.raw_data)

    async def get_video_frames(self):
        async for frame in self.client.getVideoStreamIterator(targetFormat='yuva420p'):
            logger.debug(f"Received video frame {frame} - {frame.format}")
            try:
                if self.write_avatar_video:
                    for packet in self.video_stream.encode(frame):
                        self.container.mux(packet)
                yield frame
            except:
                continue

    async def get_audio_frames(self):
        async for frame in self.client.getAudioStreamIterator():
            logger.debug(f"Received audio frame {frame} - {frame.format} - {frame.sample_rate}")
            if self.write_avatar_video:
                for packet in self.audio_stream.encode(frame):
                    self.container.mux(packet)
            yield frame
