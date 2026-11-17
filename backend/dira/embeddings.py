import hashlib
from pathlib import Path
import numpy as np
import regex
from .mechanics import normalize


def select_device(preferred="auto"):
    if preferred != "auto":
        return preferred
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


class HashEncoder:
    """Offline demonstration encoder. Not a semantic multilingual model."""

    name = "demo-feature-hash"

    def __init__(self, dimension=256):
        self.dimension = dimension
        self.device = "cpu"

    def encode(self, text):
        vector = np.zeros(self.dimension, dtype=np.float32)
        for token in regex.findall(r"\w+", normalize(text)):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            vector[int.from_bytes(digest[:4], "little") % self.dimension] += 1 if digest[4] % 2 else -1
        return vector / max(float(np.linalg.norm(vector)), 1e-9)


class LocalEncoder:
    def __init__(self, path, device="auto"):
        if not Path(path).is_dir():
            raise ValueError("embedding model must be an existing local directory")
        from sentence_transformers import SentenceTransformer

        self.device = select_device(device)
        self.model = SentenceTransformer(path, device=self.device, local_files_only=True)
        self.dimension = self.model.get_sentence_embedding_dimension()
        self.name = Path(path).name
        self.identity = (
            str(Path(path).resolve())
            + ":"
            + ":".join(
                f"{p.relative_to(path)}:{p.stat().st_size}:{p.stat().st_mtime_ns}"
                for p in sorted(Path(path).rglob("*"))
                if p.is_file()
            )
        )

    def encode(self, text):
        return self.model.encode(text, normalize_embeddings=True).astype("float32")


ANCHORS = {
    "transcript": ["What did the speaker say? speech interview statement", "ماذا قال المتحدث تصريح مقابلة"],
    "ocr": ["Read the headline ticker banner on screen", "الشريط الاخباري العنوان المكتوب على الشاشة"],
    "visual": ["Find the ship building crowd visible in the scene", "صورة مشهد سفينة مبنى حشد"],
}


class ModalityRouter:
    def __init__(self, encoder, aurelio_model=""):
        self.encoder = encoder
        self.anchors = {
            k: np.mean([encoder.encode(x) for x in texts], axis=0) for k, texts in ANCHORS.items()
        }
        self.aurelio = None
        if aurelio_model:
            from semantic_router import Route
            from semantic_router.encoders import HuggingFaceEncoder
            from semantic_router.routers import SemanticRouter
            from semantic_router.index import LocalIndex

            self.aurelio = SemanticRouter(
                encoder=HuggingFaceEncoder(name=aurelio_model, device=encoder.device),
                routes=[Route(name=k, utterances=v) for k, v in ANCHORS.items()],
                index=LocalIndex(),
                auto_sync="local",
            )

    def weights(self, query, vector, modality="auto"):
        if modality != "auto":
            return {modality: 1.0}
        if self.aurelio:
            selected = self.aurelio(query).name
        else:
            similarities = {
                k: float(np.dot(vector, v) / max(np.linalg.norm(v), 1e-9)) for k, v in self.anchors.items()
            }
            selected = max(similarities, key=similarities.get) if max(similarities.values()) > 0.15 else None
        return {k: 2.0 if k == selected else 1.0 for k in ANCHORS}
