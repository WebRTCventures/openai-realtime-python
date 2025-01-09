import asyncio
import logging
import os
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

    async def connect(self):
        await self.client.Initialize()

    async def close(self):
        await self.client.stop()

    async def send_audio(self, audio: bytes):
        await self.client.send(audio)

    async def get_video_frames(self):
        async for frame in self.client.getVideoStreamIterator(targetFormat="yuva420p"):
            yield frame

    async def get_audio_frames(self):
        async for frame in self.client.getAudioStreamIterator(targetSampleRate=24000):
            yield frame
