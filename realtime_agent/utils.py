import asyncio
import functools
import logging
from datetime import datetime
from agora_realtime_ai_api.rtc import Channel, RtcEngine, RtcOptions
from agora.rtc.video_frame_sender import ExternalVideoFrame
from av.video.frame import VideoFrame

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
        video_frame = ExternalVideoFrame()
        video_frame.buffer = frame.to_ndarray().tobytes()
        video_frame.type = 1
        video_frame.format = 1
        video_frame.stride = frame.width
        video_frame.crop_left = 0
        video_frame.crop_top = 0
        video_frame.crop_right = 0
        video_frame.crop_bottom = 0
        video_frame.rotation = 0
        video_frame.timestamp = frame.pts

        ret = self.video_frame_sender.send_video_frame(video_frame)
        logger.debug(f"Pushed video frame: {ret}, video frame length: {len(frame)}")
        if ret < 0:
            raise Exception(f"Failed to send video frame: {ret}, video frame length: {len(frame)}")
        
class AvatarRtcEngine(RtcEngine):
    def create_channel(self, options: RtcOptions) -> AvatarChannel:
        return AvatarChannel(self, options)