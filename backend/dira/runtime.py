import asyncio
from collections import deque, Counter
from datetime import timedelta
import hashlib
import logging
import shutil
from time import monotonic, perf_counter
from time import time as wall_time
from uuid import uuid4
from zoneinfo import ZoneInfo
from .models import Rule, Alert, utcnow
from .store import EvidenceStore, VectorStore
from .embeddings import HashEncoder, LocalEncoder, ModalityRouter
from .mechanics import GateEngine, SpikeDetector, rrf
from .simulation import CHANNELS, make_event
from .briefs import generate_brief

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self, queue_size=128):
        self.queues = set()
        self.queue_size, self.sequence, self.dropped = queue_size, 0, 0

    def subscribe(self):
        queue = asyncio.Queue(maxsize=self.queue_size)
        self.queues.add(queue)
        return queue

    def publish(self, kind, data):
        self.sequence += 1
        message = {"type": kind, "sequence": self.sequence, "data": data}
        for queue in tuple(self.queues):
            if queue.full():
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({"type": "resync", "sequence": self.sequence, "data": {}})
                self.dropped += 1
            else:
                queue.put_nowait(message)


class Runtime:
    def __init__(self, settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = EvidenceStore(settings.data_dir / "evidence.db")
        self.bus = EventBus()
        self.tasks, self.feed_tasks = [], []
        self.jobs = asyncio.Queue(maxsize=16)
        self.job_status = {}
        self.ingest_lock = asyncio.Lock()
        self.model_lock = asyncio.Lock()
        self.spikes = SpikeDetector()
        self.latencies = deque(maxlen=500)
        self.history = deque(maxlen=60)
        self.paused, self.counter, self.processed = False, 0, 0
        self.started = utcnow()
        # macOS monotonic time stops during sleep while wall time continues; the difference is time asleep.
        self._last_wall, self._last_mono = wall_time(), monotonic()
        self.disk_free_gb = shutil.disk_usage(settings.data_dir).free / 2**30
        self.channels = (
            [dict(c, status="simulated", playback_url="") for c in CHANNELS]
            if settings.mode == "simulation"
            else []
        )
        self.gates = GateEngine([])

    async def start(self, background=True):
        s = self.settings
        self.encoder = (
            await asyncio.to_thread(LocalEncoder, s.embedding_model, s.device)
            if s.embedding_model
            else HashEncoder(s.embedding_dimension)
        )
        identity = hashlib.sha256(
            f"{getattr(self.encoder, 'identity', self.encoder.name)}:{self.encoder.dimension}".encode()
        ).hexdigest()[:12]
        saved = self.db.objects("config")
        prior = next((x for x in saved if x["id"] == "encoder"), None)
        if prior and prior["identity"] != identity and self.db.counts()["evidence"]:
            raise ValueError("Embedding model changed: use a new DIRA_DATA_DIR to avoid mixing vector spaces")
        self.db.save("config", {"id": "encoder", "identity": identity})
        dataset = next((x for x in saved if x["id"] == "dataset"), None)
        if dataset is None:
            dataset = {"id": "dataset", "namespace": uuid4().hex}
            self.db.save("config", dataset)
            self.db.requeue_all()
        self.vectors = VectorStore(
            self.db,
            self.encoder.dimension,
            s.qdrant_url,
            s.qdrant_path or str(s.data_dir / "qdrant"),
            s.hot_capacity,
            s.hot_seconds,
            namespace=dataset["namespace"] + "_" + identity,
        )
        await self.vectors.start()
        self.router = await asyncio.to_thread(
            ModalityRouter, self.encoder, s.embedding_model if s.router == "aurelio" else ""
        )
        if not self.db.objects("config") or not any(
            x["id"] == "rules_initialized" for x in self.db.objects("config")
        ):
            for rule in [
                Rule(name="Breaking coverage", pattern="عاجل", severity="critical"),
                Rule(name="Energy watch", pattern="النفط"),
                Rule(name="Maritime activity", pattern="الموانئ", severity="info"),
            ]:
                self.db.save("rule", rule)
            self.db.save("config", {"id": "rules_initialized"})
        self.reload_rules()
        # Rehydrate only the bounded hot horizon; warm evidence remains on disk.
        recent = await asyncio.to_thread(
            self.db.recent, s.hot_capacity, utcnow() - timedelta(seconds=s.hot_seconds)
        )
        for offset in range(0, len(recent), 200):
            batch = list(reversed(recent))[offset : offset + 200]
            stored = await asyncio.to_thread(self.db.vectors_for, [str(e.id) for e in batch])
            for e in batch:
                await asyncio.to_thread(self.vectors.hot.add, e, stored[str(e.id)])
        if s.mode == "simulation" and not recent:
            for i in range(24):
                await self.ingest(make_event(i, utcnow() - timedelta(seconds=(24 - i) * 8)))
        if s.mode == "live":
            from .ingest import load_feeds, supervise_feed

            self.channels = load_feeds(s.feed_config)
            for channel in self.channels:
                saved_health = self.db.object("feed_health", channel["id"])
                if saved_health:
                    channel.update(
                        {
                            k: saved_health[k]
                            for k in ("asr_resets", "asr_skipped_seconds")
                            if k in saved_health
                        }
                    )
            if background:
                self.feed_tasks = [asyncio.create_task(supervise_feed(self, c)) for c in self.channels]
        for job in reversed(self.db.objects("job", 100)):
            self.job_status[job["id"]] = job
            if job["status"] in ("queued", "running"):
                if not self.job_allowed(job):
                    job.update(status="failed", error="Cloud policy requires a new manual request")
                    self.db.save("job", job)
                elif self.jobs.full():
                    job.update(status="failed", error="Recovery queue capacity exceeded")
                    self.db.save("job", job)
                else:
                    job["status"] = "queued"
                    self.jobs.put_nowait(job)
        if background:
            self.tasks = [
                asyncio.create_task(self.flush_loop()),
                asyncio.create_task(self.job_loop()),
                asyncio.create_task(self.scheduler()),
                asyncio.create_task(self.metrics_loop()),
            ]
            if s.mode == "simulation":
                self.tasks.append(asyncio.create_task(self.simulate()))

    def reload_rules(self):
        recent = self.gates.recent
        self.gates = GateEngine([Rule.model_validate(r) for r in self.db.objects("rule")])
        self.gates.recent = recent

    async def record_gap(self, feed, reason, estimate, bounds_estimated=True):
        now = utcnow()
        gap = {
            "id": str(uuid4()),
            "channel_id": feed["id"],
            "detected_at": now.isoformat(),
            "reason": reason,
            "estimated_lost_seconds": estimate,
            "bounds_estimated": bounds_estimated,
            "start": (now - timedelta(seconds=estimate)).isoformat() if estimate is not None else None,
            "end": now.isoformat(),
            "note": "Coverage interruption; duration is an estimate, not measured lost speech."
            if bounds_estimated
            else "Coverage interruption measured from host clocks (precision about one metrics tick).",
        }
        await asyncio.to_thread(self.db.save, "gap", gap)
        await asyncio.to_thread(
            self.db.save,
            "feed_health",
            {
                "id": feed["id"],
                "asr_resets": feed.get("asr_resets", 0),
                "asr_skipped_seconds": feed.get("asr_skipped_seconds", 0),
            },
        )
        self.bus.publish("gap", gap)

    async def check_host_sleep(self, threshold=10.0):
        """Record one measured `host_sleep` gap per live channel when the host slept since the last check."""
        wall, mono = wall_time(), monotonic()
        slept = (wall - self._last_wall) - (mono - self._last_mono)
        self._last_wall, self._last_mono = wall, mono
        if slept <= threshold:
            return 0
        log.warning("Host slept for about %.0fs; recording coverage gaps", slept)
        for channel in self.channels:
            if channel.get("status") != "simulated":
                await self.record_gap(channel, "host_sleep", round(slept, 1), bounds_estimated=False)
        return slept

    async def health_alert(self, feed, detail):
        alert = Alert(
            tdo_id=None,
            channel_id=feed["id"],
            rule_name="Speech recognition degraded",
            severity="warning",
            detail=detail,
            kind="health",
        )
        await asyncio.to_thread(self.db.save, "alert", alert)
        self.bus.publish("alert", alert.model_dump(mode="json"))

    async def encode_event(self, e):
        async with self.model_lock:
            vectors = {}
            for modality in ("transcript", "ocr", "visual"):
                text = getattr(e, modality)
                if modality == "transcript":
                    text += " " + e.translation
                if text.strip():
                    vectors[modality] = (await asyncio.to_thread(self.encoder.encode, text)).tolist()
            return vectors

    async def ingest(self, event):
        async with self.ingest_lock:
            if self.db.get(str(event.id)):
                return False
            if self.disk_free_gb < self.settings.min_disk_free_gb:
                raise OverflowError("disk reserve reached; ingestion paused until space is available")
            if self.db.counts()["pending"] >= self.settings.outbox_limit:
                raise OverflowError("warm-store backlog full; retry after recovery")
            start = perf_counter()
            vectors = await self.encode_event(event)
            if not vectors:
                raise ValueError("observation must contain text, OCR or a visual description")
            if not await self.vectors.add(event, vectors):
                return False
            alerts = self.gates.evaluate(event)
            vector = next(iter(vectors.values()))
            spike = self.spikes.observe(vector, perf_counter())
            if spike:
                alerts.append(
                    Alert(
                        tdo_id=event.id,
                        channel_id=event.channel_id,
                        rule_name="Semantic volume spike",
                        severity="warning",
                        detail=f"Arrival-rate topic volume {spike['z_score']}σ above baseline; {spike['count']} observations.",
                        kind="spike",
                        simulated=event.simulated,
                    )
                )
            for a in alerts:
                await asyncio.to_thread(self.db.save, "alert", a)
                self.bus.publish("alert", a.model_dump(mode="json"))
            self.processed += 1
            self.latencies.append((perf_counter() - start) * 1000)
            self.bus.publish("tdo", event.model_dump(mode="json"))
            return True

    async def search(self, request):
        start = perf_counter()
        async with self.model_lock:
            vector = await asyncio.to_thread(self.encoder.encode, request.query)
            weights = await asyncio.to_thread(self.router.weights, request.query, vector, request.modality)
        lists = await asyncio.gather(*(self.vectors.search(vector.tolist(), m, request) for m in weights))
        lexical = await asyncio.to_thread(self.db.lexical, request)
        lists.append(lexical)
        records = {str(e.id): e for group in lists for e in group}
        ranking = rrf([[str(e.id) for e in group] for group in lists], weights=[*weights.values(), 1.5])
        from .text import normalize
        import numpy as np

        stored = await asyncio.to_thread(self.db.vectors_for, [key for key, _ in ranking])
        results, seen = [], set()
        for key, score in ranking:
            event = records[key]
            fingerprint = (event.channel_id, " ".join(normalize(event.text()).split()))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            similarities = [
                float(np.dot(vector, v) / max(np.linalg.norm(vector) * np.linalg.norm(v), 1e-9))
                for modality, v in stored.get(key, {}).items()
                if modality in weights
            ]
            results.append(
                {
                    "event": event.model_dump(mode="json"),
                    "score": score,
                    "cosine_similarity": round(max(similarities), 4) if similarities else None,
                    "lexical_match": any(str(e.id) == key for e in lexical),
                }
            )
            if len(results) >= request.limit:
                break
        return {
            "results": results,
            "elapsed_ms": round((perf_counter() - start) * 1000, 2),
            "weights": weights,
            "vector_similarity_floor": request.min_similarity,
            "lexical_candidate_limit": 10000,
            "encoder": self.encoder.name,
            "warm_available": self.vectors.ready,
            "warm_error": bool(self.vectors.error),
        }

    def job_allowed(self, job):
        return not (
            self.settings.llm_provider == "cloud"
            and self.settings.llm_url
            and not self.settings.cloud_auto_briefs
            and job.get("trigger") != "manual"
        )

    def enqueue_brief(self, kind, trigger="manual"):
        if self.jobs.full():
            raise OverflowError("brief queue full")
        job = {"id": str(uuid4()), "kind": kind, "status": "queued", "trigger": trigger}
        # Keep only a bounded recent job registry.
        if len(self.job_status) >= 100:
            completed = next(
                (k for k, v in self.job_status.items() if v["status"] in ("done", "failed")), None
            )
            if completed:
                self.job_status.pop(completed)
        self.job_status[job["id"]] = job
        self.db.save("job", job)
        self.jobs.put_nowait(job)
        self.bus.publish("job", job.copy())
        return job

    async def process_job(self, job):
        if not self.job_allowed(job):
            job.update(status="failed", error="Cloud policy requires a new manual request")
            self.db.save("job", job)
            self.bus.publish("job", job.copy())
            return
        job["status"] = "running"
        self.db.save("job", job)
        self.bus.publish("job", job.copy())
        try:
            hours = 24 if job["kind"] == "morning" else 1
            now = utcnow()
            events, coverage = await asyncio.to_thread(
                self.db.brief_sample, now - timedelta(hours=hours), now, 80
            )
            brief = await generate_brief(events, job["kind"], self.settings, coverage)
            await asyncio.to_thread(self.db.save, "brief", brief)
            job.update(status="done", brief_id=str(brief.id))
            self.bus.publish("brief", brief.model_dump(mode="json"))
        except Exception as exc:
            job.update(status="failed", error=type(exc).__name__)
            log.exception("Brief job failed")
        self.db.save("job", job)
        self.bus.publish("job", job.copy())

    async def job_loop(self):
        while True:
            job = await self.jobs.get()
            try:
                await self.process_job(job)
            finally:
                self.jobs.task_done()

    async def scheduler(self):
        last_narrative = utcnow()
        while True:
            await asyncio.sleep(30)
            now = utcnow()
            if (
                self.settings.llm_provider == "cloud"
                and self.settings.llm_url
                and not self.settings.cloud_auto_briefs
            ):
                continue
            local = now.astimezone(ZoneInfo("Asia/Kuwait"))
            key = "morning-" + local.date().isoformat()
            already = any(x["id"] == key for x in self.db.objects("schedule", 60))
            if local.hour >= self.settings.brief_hour and not already and not self.jobs.full():
                self.enqueue_brief("morning", trigger="scheduled")
                self.db.save("schedule", {"id": key})
            if (
                now - last_narrative
            ).total_seconds() >= self.settings.narrative_interval and not self.jobs.full():
                self.enqueue_brief("narrative", trigger="scheduled")
                last_narrative = now

    async def flush_loop(self):
        while True:
            await self.vectors.flush()
            await asyncio.sleep(2)

    async def metrics_loop(self):
        while True:
            try:
                await self.check_host_sleep()
            except Exception:
                log.exception("Host sleep bookkeeping failed")
            self.disk_free_gb = (
                await asyncio.to_thread(shutil.disk_usage, self.settings.data_dir)
            ).free / 2**30
            self.history.append(
                {
                    "time": utcnow().isoformat(),
                    "events": self.processed,
                    "latency_ms": round(self.latencies[-1], 2) if self.latencies else 0,
                }
            )
            self.bus.publish("metrics", self.metrics())
            # Channel health (status, ASR lag) changes outside any event; refresh browsers every tick.
            if self.channels:
                self.bus.publish("channels", self.channels)
            await asyncio.sleep(3)

    async def simulate(self):
        while True:
            await asyncio.sleep(self.settings.simulation_interval)
            if not self.paused:
                try:
                    await self.ingest(make_event(self.counter))
                    self.counter += 1
                    if self.counter % 64 == 48:
                        for _ in range(8):
                            if self.paused:
                                break
                            await self.ingest(make_event(3))
                            await asyncio.sleep(0.15)
                except OverflowError:
                    log.warning("Simulation paused by ingestion backpressure")

    def metrics(self):
        import numpy as np

        return {
            **self.db.counts(),
            "hot_vectors": len(self.vectors.hot.records),
            "hot_capacity": self.settings.hot_capacity,
            "hot_horizon_seconds": max(
                0,
                (
                    utcnow() - min((e.start for e in self.vectors.hot.records.values()), default=utcnow())
                ).total_seconds(),
            ),
            "disk_free_gb": round(self.disk_free_gb, 2),
            "disk_guard_active": self.disk_free_gb < self.settings.min_disk_free_gb,
            "active_alerts": self.db.active_alert_count(),
            "spike_clock": "arrival-monotonic",
            "alert_duplicates_suppressed": self.gates.suppressed,
            "latency_p95_ms": round(float(np.percentile(self.latencies, 95)), 2) if self.latencies else 0,
            "asr_lag_max_seconds": max(
                (c["asr_lag_seconds"] for c in self.channels if c.get("asr_lag_seconds") is not None),
                default=None,
            ),
            "asr_max_lag": self.settings.asr_max_lag,
            "processed": self.processed,
            "uptime_seconds": int((utcnow() - self.started).total_seconds()),
            "device": self.encoder.device,
            "encoder": self.encoder.name,
            "warm_status": "connected" if self.vectors.ready and not self.vectors.error else "degraded",
            "llm": self.settings.llm_provider if self.settings.llm_url else "extractive",
            "cloud_auto_briefs": self.settings.cloud_auto_briefs,
            "mode": self.settings.mode,
            "paused": self.paused,
            "ws_resyncs": self.bus.dropped,
            "regex_timeouts": self.gates.timeouts,
            "history": list(self.history),
            "jobs_pending": self.jobs.qsize(),
        }

    def snapshot(self):
        return {
            "channels": self.channels,
            "events": [e.model_dump(mode="json") for e in self.db.recent(120)],
            "alerts": self.db.objects("alert", 100),
            "briefs": self.db.objects("brief", 20),
            "rules": self.db.objects("rule"),
            "jobs": self.job_status,
            "metrics": self.metrics(),
            "sequence": self.bus.sequence,
        }

    def graph(self):
        counts, edges = Counter(), Counter()
        for e in self.db.recent(300):
            names = sorted({x.name for x in e.entities})
            counts.update(names)
            for i, a in enumerate(names):
                for b in names[i + 1 :]:
                    edges[(a, b)] += 1
        return {
            "nodes": [{"id": n, "count": c} for n, c in counts.most_common(30)],
            "edges": [{"source": a, "target": b, "weight": v} for (a, b), v in edges.most_common(60)],
        }

    async def stop(self):
        for task in self.tasks + self.feed_tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, *self.feed_tasks, return_exceptions=True)
        try:
            await asyncio.wait_for(self.vectors.flush(), timeout=5)
        except (Exception, asyncio.TimeoutError):
            log.warning("Shutdown left pending evidence in durable outbox")
        await self.vectors.close()
        self.db.close()
