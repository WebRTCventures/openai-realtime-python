import asyncio
import functools
import logging
import os
from datetime import datetime
from agora_realtime_ai_api.rtc import Channel, RtcEngine, RtcOptions
from agora.rtc.video_encoded_image_sender import EncodedVideoFrameInfo
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
    def __init__(self, rtc: "RtcEngine", options: RtcOptions) -> None:
        super().__init__(rtc, options)
        self.video_frame_sender = (
            self.media_node_factory.create_video_encoded_image_sender()
        )
        self.sender_options = SenderOptions(0, 2, 640)
        self.video_track = self.rtc.agora_service.create_custom_video_track_encoded(
            self.video_frame_sender,
            self.sender_options
        )
        self.video_track.set_enabled(1)
        self.local_user.publish_video(self.video_track)

    async def push_video_frame(self, frame: VideoFrame) -> None:
        """
        Pushes a video frame to the remote user.

        Args:
            frame (VideoFrame): The video frame to be pushed.
        """
        is_keyframe = frame.key_frame
        encoded_video_frame_info = EncodedVideoFrameInfo()
        encoded_video_frame_info.codec_type = 2
        encoded_video_frame_info.width = frame.width
        encoded_video_frame_info.height = frame.height
        encoded_video_frame_info.frames_per_second = 25
        if is_keyframe:
            encoded_video_frame_info.frame_type = 3
        else:
            encoded_video_frame_info.frame_type = 4
        for plane in frame.planes:
            ret = self.video_frame_sender.send_encoded_video_image(
                plane.buffer_ptr, plane.buffer_size, encoded_video_frame_info
            )
            logger.info(f"Pushed video frame: {ret}")
            if ret < 0:
                raise Exception(f"Failed to send video frame: {ret}")
        
    async def push_audio_frame(self, frame: AudioFrame) -> None:
        """
        Pushes an audio frame to the channel
        
        Parameters:
            frame: The audio frame to push
        """
        frame_tobytes = frame.to_ndarray().tobytes()
        audio_frame = PcmAudioFrame()
        audio_frame.data = bytearray(frame_tobytes)
        audio_frame.timestamp = 0
        audio_frame.bytes_per_sample = 2
        audio_frame.number_of_channels = self.options.channels
        audio_frame.sample_rate = self.options.sample_rate
        audio_frame.samples_per_channel = int(
            len(frame_tobytes) / audio_frame.bytes_per_sample / audio_frame.number_of_channels
        )
        ret = self.audio_pcm_data_sender.send_audio_pcm_data(audio_frame)
        logger.debug(f"Pushed audio frame: {ret}, audio frame length: {len(frame_tobytes)}")
        if ret < 0:
            raise Exception(f"Failed to send audio frame: {ret}")
        
class AvatarRtcEngine(RtcEngine):
    def __init__(self, appid: str, appcert: str):
        self.appid = appid
        self.appcert = appcert

        if not appid:
            raise Exception("App ID is required)")

        config = AgoraServiceConfig()
        config.enable_video = 1
        config.audio_scenario = AudioScenarioType.AUDIO_SCENARIO_CHORUS
        config.appid = appid
        config.log_path = os.path.join(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.join(os.path.abspath(__file__)))
                )
            ),
            "agorasdk.log",
        )
        self.agora_service = AgoraService()
        self.agora_service.initialize(config)

    def create_channel(self, options: RtcOptions) -> AvatarChannel:
        return AvatarChannel(self, options)