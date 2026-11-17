import asyncio
import hashlib
from collections import OrderedDict
from datetime import timedelta
import json
import sqlite3
import threading
import logging
import struct
import re
from pathlib import Path
import faiss
import numpy as np
from qdrant_client import AsyncQdrantClient, models
from .models import TDO, utcnow

log = logging.getLogger(__name__)
MODALITIES = ("transcript", "ocr", "visual")


def encode_vectors(vectors):
    """Versioned little-endian float32 payload, independent of pickle/numpy archives."""
    header = json.dumps([(name, len(values)) for name, values in vectors.items()]).encode()
    body = b"".join(np.asarray(v, dtype="<f4").tobytes() for v in vectors.values())
    return b"DV1" + struct.pack("<I", len(header)) + header + body


def decode_vectors(payload):
    if isinstance(payload, str):  # Existing archives remain recoverable without rewriting them.
        return json.loads(payload)
    if payload[:3] != b"DV1":
        raise ValueError("unknown vector encoding")
    size = struct.unpack("<I", payload[3:7])[0]
    header, offset, result = json.loads(payload[7 : 7 + size]), 7 + size, {}
    for name, length in header:
        result[name] = np.frombuffer(payload, dtype="<f4", count=length, offset=offset).tolist()
        offset += length * 4
    if offset != len(payload):
        raise ValueError("invalid vector payload length")
    return result


class EvidenceStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, start REAL, end REAL, channel TEXT, payload TEXT NOT NULL, vectors TEXT NOT NULL, pending INTEGER NOT NULL DEFAULT 1);
            CREATE INDEX IF NOT EXISTS evidence_time ON evidence(start DESC);
            CREATE INDEX IF NOT EXISTS outbox ON evidence(pending, start);
            CREATE TABLE IF NOT EXISTS objects(kind TEXT, id TEXT, payload TEXT NOT NULL, PRIMARY KEY(kind,id));
        """)
        self.db.commit()
        count, pending = self.db.execute("SELECT COUNT(*),COALESCE(SUM(pending),0) FROM evidence").fetchone()
        self._counts = {"evidence": count, "pending": pending}

    def insert(self, event, vectors):
        with self.lock:
            with self.db:
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?,1)",
                    (
                        str(event.id),
                        event.start.timestamp(),
                        event.end.timestamp(),
                        event.channel_id,
                        event.model_dump_json(),
                        encode_vectors(vectors),
                    ),
                )
                added = cursor.rowcount > 0
            if added:
                self._counts["evidence"] += 1
                self._counts["pending"] += 1
            return added

    def get(self, key):
        with self.lock:
            row = self.db.execute("SELECT payload FROM evidence WHERE id=?", (key,)).fetchone()
        return TDO.model_validate_json(row[0]) if row else None

    def recent(self, limit=100, since=None):
        with self.lock:
            rows = self.db.execute(
                "SELECT payload FROM evidence WHERE start>=? ORDER BY start DESC LIMIT ?",
                (since.timestamp() if since else 0, limit),
            ).fetchall()
        return [TDO.model_validate_json(r[0]) for r in rows]

    def vectors_for(self, keys):
        if not keys:
            return {}
        with self.lock:
            rows = self.db.execute(
                "SELECT id,vectors FROM evidence WHERE id IN (" + ",".join("?" for _ in keys) + ")", keys
            ).fetchall()
        return {key: decode_vectors(payload) for key, payload in rows}

    def pending(self, limit=128):
        with self.lock:
            return self.db.execute(
                "SELECT id,payload,vectors FROM evidence WHERE pending=1 ORDER BY start LIMIT ?", (limit,)
            ).fetchall()

    def counts(self):
        with self.lock:
            return dict(self._counts)

    def requeue_all(self):
        with self.lock:
            with self.db:
                self.db.execute("UPDATE evidence SET pending=1 WHERE pending=0")
            self._counts["pending"] = self._counts["evidence"]

    def ack(self, ids):
        with self.lock:
            with self.db:
                changed = self.db.executemany(
                    "UPDATE evidence SET pending=0 WHERE id=? AND pending=1", [(i,) for i in ids]
                ).rowcount
            self._counts["pending"] -= changed

    def brief_sample(self, since, until, limit=80):
        """Stratify across time and channel, independent of a channel's output rate."""
        start, end = since.timestamp(), until.timestamp()
        with self.lock:
            stats = self.db.execute(
                "SELECT COUNT(*),MIN(start),MAX(start),COUNT(DISTINCT channel) FROM evidence WHERE start BETWEEN ? AND ?",
                (start, end),
            ).fetchone()
            buckets = max(1, min(24, limit // max(1, stats[3])))
            width = max(1.0, (end - start) / buckets)
            rows = self.db.execute(
                """
                WITH bucketed AS (
                    SELECT payload,channel,start,MIN(?,CAST((start-?)/? AS INTEGER)) AS bucket
                    FROM evidence WHERE start BETWEEN ? AND ?
                ), ranked AS (
                    SELECT *,ROW_NUMBER() OVER(PARTITION BY channel,bucket ORDER BY start DESC) AS n
                    FROM bucketed
                ) SELECT payload FROM ranked ORDER BY n,bucket,channel LIMIT ?
            """,
                (buckets - 1, start, width, start, end, limit),
            ).fetchall()
        events = [TDO.model_validate_json(row[0]) for row in rows]
        coverage = {
            "window_start": since.isoformat(),
            "window_end": until.isoformat(),
            "total_observations": stats[0],
            "sampled_observations": len(events),
            "available_channels": stats[3],
            "sampled_channels": len({e.channel_id for e in events}),
            "first_sample": min((e.start for e in events), default=None),
            "last_sample": max((e.start for e in events), default=None),
            "method": "time-channel-stratified",
            "exhaustive": stats[0] == len(events),
        }
        for key in ("first_sample", "last_sample"):
            if coverage[key] is not None:
                coverage[key] = coverage[key].isoformat()
        return events, coverage

    def object(self, kind, key):
        with self.lock:
            row = self.db.execute("SELECT payload FROM objects WHERE kind=? AND id=?", (kind, key)).fetchone()
        return json.loads(row[0]) if row else None

    def active_alert_count(self):
        with self.lock:
            return self.db.execute(
                "SELECT COUNT(*) FROM objects WHERE kind='alert' AND COALESCE(json_extract(payload,'$.acknowledged'),0)=0"
            ).fetchone()[0]

    def save(self, kind, obj):
        payload = obj.model_dump(mode="json") if hasattr(obj, "model_dump") else obj
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO objects VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload",
                (kind, str(payload["id"]), json.dumps(payload)),
            )

    def objects(self, kind, limit=500):
        with self.lock:
            rows = self.db.execute(
                "SELECT payload FROM objects WHERE kind=? ORDER BY rowid DESC LIMIT ?", (kind, limit)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def delete(self, kind, key):
        with self.lock, self.db:
            self.db.execute("DELETE FROM objects WHERE kind=? AND id=?", (kind, key))

    def lexical(self, request):
        # Bounded candidate scan of durable evidence; FTS is a deployment upgrade for million-record archives.
        with self.lock:
            rows = self.db.execute(
                "SELECT payload FROM evidence WHERE start<=? AND end>=? AND (? IS NULL OR channel=?) ORDER BY start DESC LIMIT 10000",
                (
                    request.until.timestamp() if request.until else 1e20,
                    request.since.timestamp() if request.since else 0,
                    request.channel_id,
                    request.channel_id,
                ),
            ).fetchall()
        from .mechanics import normalize

        stopwords = set(
            "a an the in on at of to for and or is are was were with from by this that it as عن في من الى الي علي على و أو او ان إن هذا هذه مع هل ما الذي التي كان يكون".split()
        )
        terms = set(re.findall(r"\w+", normalize(request.query))) - stopwords
        scored = []
        for row in rows:
            e = TDO.model_validate_json(row[0])
            if request.accepts(e):
                text = e.text() if request.modality == "auto" else getattr(e, request.modality)
                if request.modality == "transcript":
                    text += " " + e.translation
                words = set(re.findall(r"\w+", normalize(text)))
                score = len(terms & words)
                if score:
                    scored.append((score, e))
        return [e for _, e in sorted(scored, key=lambda x: -x[0])[: request.limit * 3]]

    def close(self):
        self.db.close()


class HotIndex:
    def __init__(self, dimension, capacity=4000, seconds=7200):
        self.dimension, self.capacity, self.seconds = dimension, capacity, seconds
        self.records = OrderedDict()
        self.vectors = {}
        self.indices = {m: faiss.IndexIDMap2(faiss.IndexFlatIP(dimension)) for m in MODALITIES}
        self.ids, self.reverse = {}, {}
        self.counter = 0
        self.lock = threading.RLock()

    def add(self, event, vectors):
        key = str(event.id)
        with self.lock:
            if key in self.records:
                return
            cutoff = utcnow() - timedelta(seconds=self.seconds)
            for old in list(self.records):
                if self.records[old].end < cutoff or len(self.records) >= self.capacity:
                    index_id = self.ids.pop(old)
                    for index in self.indices.values():
                        index.remove_ids(np.array([index_id], dtype=np.int64))
                    self.reverse.pop(index_id)
                    self.records.pop(old)
                    self.vectors.pop(old)
            if event.end < cutoff:
                return
            self.counter += 1
            self.records[key], self.vectors[key] = event, vectors
            self.ids[key], self.reverse[self.counter] = self.counter, key
            for modality, vector in vectors.items():
                v = np.array([vector], dtype=np.float32)
                faiss.normalize_L2(v)
                self.indices[modality].add_with_ids(v, np.array([self.counter], dtype=np.int64))

    def search(self, vector, modality, request):
        query = np.array([vector], dtype=np.float32)
        faiss.normalize_L2(query)
        with self.lock:
            cutoff = utcnow() - timedelta(seconds=self.seconds)
            # Pre-filter avoids missing valid low-ranked hits behind other channels.
            keys = [
                k
                for k, e in self.records.items()
                if request.accepts(e) and e.end >= cutoff and modality in self.vectors[k]
            ]
            if not keys:
                return []
            if len(keys) == self.indices[modality].ntotal:
                scores, indices = self.indices[modality].search(query, min(len(keys), request.limit * 3))
                return [
                    self.reverse[int(i)]
                    for score, i in zip(scores[0], indices[0])
                    if i >= 0 and score >= request.min_similarity
                ]
            matrix = np.asarray([self.vectors[k][modality] for k in keys], dtype=np.float32)
            faiss.normalize_L2(matrix)
            scores = matrix @ query[0]
            return [
                keys[int(i)]
                for i in np.argsort(-scores)[: request.limit * 3]
                if scores[i] >= request.min_similarity
            ]


class VectorStore:
    def __init__(
        self, db, dimension, qdrant_url="", qdrant_path="", capacity=4000, seconds=7200, namespace="demo"
    ):
        self.db, self.dimension = db, dimension
        self.hot = HotIndex(dimension, capacity, seconds)
        self.client = (
            AsyncQdrantClient(url=qdrant_url, timeout=3)
            if qdrant_url
            else AsyncQdrantClient(path=qdrant_path or ":memory:")
        )
        self.collection = f"dira_{namespace}_{dimension}"
        self.target_identity = hashlib.sha256(
            f"{qdrant_url or qdrant_path}:{self.collection}".encode()
        ).hexdigest()
        self.ready, self.error = False, None
        self.flush_lock = asyncio.Lock()

    async def start(self):
        try:
            created = not await self.client.collection_exists(self.collection)
            if created:
                await self.client.create_collection(
                    self.collection,
                    vectors_config={
                        m: models.VectorParams(size=self.dimension, distance=models.Distance.COSINE)
                        for m in MODALITIES
                    },
                )
            prior = next((x for x in self.db.objects("config") if x["id"] == "warm_target"), None)
            if created or not prior or prior["identity"] != self.target_identity:
                await asyncio.to_thread(self.db.requeue_all)
                self.db.save("config", {"id": "warm_target", "identity": self.target_identity})
            self.ready, self.error = True, None
        except Exception as exc:
            self.error = str(exc)
            log.warning("Warm tier unavailable: %s", type(exc).__name__)

    async def add(self, event, vectors):
        for modality, vector in vectors.items():
            if modality not in MODALITIES or len(vector) != self.dimension or not np.isfinite(vector).all():
                raise ValueError("invalid vector modality, dimensions or finite values")
        added = await asyncio.to_thread(self.db.insert, event, vectors)
        if added:
            await asyncio.to_thread(self.hot.add, event, vectors)
        return added

    async def flush(self):
        async with self.flush_lock:
            if not self.ready:
                await self.start()
            if not self.ready:
                return
            rows = await asyncio.to_thread(self.db.pending)
            if not rows:
                return
            try:
                points = []
                for key, payload, vectors in rows:
                    event = TDO.model_validate_json(payload)
                    points.append(
                        models.PointStruct(
                            id=key,
                            vector=decode_vectors(vectors),
                            payload={
                                **event.model_dump(mode="json"),
                                "start_epoch": event.start.timestamp(),
                                "end_epoch": event.end.timestamp(),
                            },
                        )
                    )
                await self.client.upsert(self.collection, points=points, wait=True)
                await asyncio.to_thread(self.db.ack, [r[0] for r in rows])
                self.error = None
            except Exception as exc:
                self.ready, self.error = False, str(exc)
                log.warning("Warm flush deferred: %s", type(exc).__name__)

    async def search(self, vector, modality, request):
        keys = await asyncio.to_thread(self.hot.search, vector, modality, request)
        records = {k: self.hot.records[k] for k in keys if k in self.hot.records}
        conditions = []
        for field in ("channel_id", "language", "speaker"):
            if value := getattr(request, field):
                conditions.append(models.FieldCondition(key=field, match=models.MatchValue(value=value)))
        if request.since:
            conditions.append(
                models.FieldCondition(key="end_epoch", range=models.Range(gte=request.since.timestamp()))
            )
        if request.until:
            conditions.append(
                models.FieldCondition(key="start_epoch", range=models.Range(lte=request.until.timestamp()))
            )
        warm_keys = []
        if self.ready:
            try:
                response = await self.client.query_points(
                    self.collection,
                    query=vector,
                    using=modality,
                    score_threshold=request.min_similarity,
                    query_filter=models.Filter(must=conditions) if conditions else None,
                    limit=request.limit * 3,
                )
                for p in response.points:
                    key = str(p.id)
                    records[key] = TDO.model_validate(p.payload)
                    warm_keys.append(key)
            except Exception as exc:
                self.error = str(exc)
        from .mechanics import rrf

        return [records[k] for k, _ in rrf([keys, warm_keys])]

    async def close(self):
        await self.client.close()
