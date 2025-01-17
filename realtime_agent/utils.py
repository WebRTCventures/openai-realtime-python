import asyncio
import functools
import logging
import os
from datetime import datetime
from agora_realtime_ai_api.rtc import Channel, RtcEngine, RtcOptions
from agora.rtc.video_frame_sender import ExternalVideoFrame
from agora.rtc.audio_pcm_data_sender import PcmAudioFrame
from agora.rtc.agora_base import AudioScenarioType
from agora.rtc.agora_service import AgoraService, AgoraServiceConfig, SenderOptions
from av.video.frame import VideoFrame
from av.audio.frame import AudioFrame

from .logger import setup_logger

logger = setup_logger(__name__, log_level=logging.INFO)

def write_pcm_to_file(buffer: bytearray, file_name: str) -> None:
    """Helper function to write PCM data to a file."""
    with open(file_name, "ab") as f:  # append to file
        f.write(buffer)


def generate_file_name(prefix: str) -> str:
    # Create a timestamp for the file name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.pcm"


class PCMWriter:
    def __init__(self, prefix: str, write_pcm: bool, buffer_size: int = 1024 * 64):
        self.write_pcm = write_pcm
        self.buffer = bytearray()
        self.buffer_size = buffer_size
        self.file_name = generate_file_name(prefix) if write_pcm else None
        self.loop = asyncio.get_event_loop()

    async def write(self, data: bytes) -> None:
        """Accumulate data into the buffer and write to file when necessary."""
        if not self.write_pcm:
            return

        self.buffer.extend(data)

        # Write to file if buffer is full
        if len(self.buffer) >= self.buffer_size:
            await self._flush()

    async def flush(self) -> None:
        """Write any remaining data in the buffer to the file."""
        if self.write_pcm and self.buffer:
            await self._flush()

    async def _flush(self) -> None:
        """Helper method to write the buffer to the file."""
        if self.file_name:
            await self.loop.run_in_executor(
                None,
                functools.partial(write_pcm_to_file, self.buffer[:], self.file_name),
            )
        self.buffer.clear()

class AvatarChannel(Channel):
    def __init__(self, rtc: "AvatarRtcEngine", options: RtcOptions) -> None:
        super().__init__(rtc, options)
        self.video_frame_sender = (
            self.media_node_factory.create_video_frame_sender()
        )
        self.video_track = self.rtc.agora_service.create_custom_video_track_frame(
            self.video_frame_sender
        )
        self.video_track.set_enabled(1)
        self.local_user.publish_video(self.video_track)

    async def push_video_frame(self, frame: VideoFrame) -> None:
        """
        Pushes a video frame to the remote user.

        Args:
            frame (VideoFrame): The video frame to be pushed.
        """
        np_array = frame.to_ndarray()
        byte_data = bytearray(np_array.tobytes())

        logger.debug(f"Pushing video frame with shape: {np_array.shape}")

        external_video_frame = ExternalVideoFrame()
        external_video_frame.buffer = byte_data
        external_video_frame.type = 1
        external_video_frame.format = 1
        external_video_frame.stride = frame.width
        external_video_frame.height = frame.height
        external_video_frame.timestamp = 0
        external_video_frame.metadata = "avatar video frame"

        ret = self.video_frame_sender.send_video_frame(external_video_frame)

        logger.debug(f"Pushed video frame: {ret}")
        if ret < 0:
            raise Exception(f"Failed to send video frame: {ret}")
        
    async def push_audio_frame(self, frame: AudioFrame) -> None:
        """
        Pushes an audio frame to the channel
        
        Parameters:
            frame: The audio frame to push
        """
        pcm_array = frame.to_ndarray()
        pcm_bytes = pcm_array.tobytes()
        pcm_data = bytearray(pcm_bytes)

        logger.debug(f"Pushing audio frame with shape: {pcm_array.shape}")

        audio_frame = PcmAudioFrame()
        audio_frame.data = pcm_data
        audio_frame.timestamp = 0
        audio_frame.bytes_per_sample = 2
        audio_frame.number_of_channels = 1
        audio_frame.sample_rate = 96000
        audio_frame.samples_per_channel = int(
            len(pcm_bytes) / audio_frame.bytes_per_sample / audio_frame.number_of_channels
        )
        ret = self.audio_pcm_data_sender.send_audio_pcm_data(audio_frame)
        logger.debug(f"Pushed audio frame: {ret}")
        if ret < 0:
            raise Exception(f"Failed to send audio frame: {ret}")
        
class AvatarRtcEngine(RtcEngine):
    def __init__(self, appid: str, appcert: str):
        self.appid = appid
        self.appcert = appcert

        if not appid:
            raise Exception("App ID is required)")

        config = AgoraServiceConfig()
        config.audio_scenario = AudioScenarioType.AUDIO_SCENARIO_CHORUS
        config.appid = appid
        config.log_path = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.join(os.path.abspath(__file__)))
            ),
            "agorasdk.log",
        )
        self.agora_service = AgoraService()
        self.agora_service.initialize(config)

    def create_channel(self, options: RtcOptions) -> AvatarChannel:
        return AvatarChannel(self, options)