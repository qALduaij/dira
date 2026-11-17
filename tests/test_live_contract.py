import asyncio
import json
import shutil
import subprocess
from types import SimpleNamespace
import pytest
import websockets
from dira.ingest import audio_session


@pytest.mark.asyncio
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not installed")
async def test_ffmpeg_pcm_to_local_asr_websocket(tmp_path):
    wav = tmp_path / "audio.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.3",
            "-ar",
            "16000",
            str(wav),
        ],
        check=True,
    )
    observations = []
    received = []

    async def asr(ws):
        await ws.send(json.dumps({"type": "config", "useAudioWorklet": True}))
        async for data in ws:
            received.append(data)
            if not data:
                await ws.send(
                    json.dumps(
                        {
                            "lines": [
                                {
                                    "start": "0:00:00",
                                    "end": "0:00:00.3",
                                    "speaker": 1,
                                    "text": "Local ASR contract test",
                                }
                            ]
                        }
                    )
                )
                await ws.send(json.dumps({"type": "ready_to_stop"}))
                break

    async with websockets.serve(asr, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]

        class Runtime:
            settings = SimpleNamespace(asr_url=f"ws://127.0.0.1:{port}/asr")

            async def ingest(self, event):
                observations.append(event)

        await asyncio.wait_for(audio_session(Runtime(), {"id": "test", "input_url": str(wav)}), 5)
    assert sum(map(len, received)) > 0
    assert len(observations) == 1
    assert observations[0].transcript == "Local ASR contract test"
    assert observations[0].speaker is None  # A default ASR speaker ID is not diarization.
    assert (observations[0].end - observations[0].start).total_seconds() == 0.3
