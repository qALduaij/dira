"""Keep Paddle native kernels and their GIL/OpenMP state out of the API process."""

import asyncio
import json
import sys
from contextlib import suppress


class OCRProcess:
    def __init__(self, process):
        self.process = process
        self.stats = {}
        self.exchange_timeout = 30
        self.close_timeout = 5

    @classmethod
    async def start(cls, model_dir, detector, recognizer, threads):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "dira.ocr_worker",
            "--model-dir",
            str(model_dir),
            "--detector",
            detector,
            "--recognizer",
            recognizer,
            "--threads",
            str(threads),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        worker = cls(process)
        try:
            response = await asyncio.wait_for(process.stdout.readline(), 90)
            if not json.loads(response).get("ready"):
                raise RuntimeError("OCR worker did not initialize")
            return worker
        except BaseException:
            await worker.close()
            raise

    async def extract(self, raw):
        try:
            async with asyncio.timeout(self.exchange_timeout):
                self.process.stdin.write(raw)
                await self.process.stdin.drain()
                response = await self.process.stdout.readline()
        except TimeoutError:
            self.stats["timeouts"] = self.stats.get("timeouts", 0) + 1
            raise
        if not response:
            raise RuntimeError("OCR worker exited")
        payload = json.loads(response)
        self.stats = payload.get("stats", {})
        return payload["text"]

    async def close(self):
        self.process.stdin.close()
        try:
            await asyncio.wait_for(self.process.wait(), self.close_timeout)
        except TimeoutError:
            with suppress(ProcessLookupError):
                self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    self.process.kill()
                await self.process.wait()
