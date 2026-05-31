import json
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
from .file_store import iter_rag_docs, BASE


class RAGStore:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.docs = []          # texts, parallel to FAISS rows
        self.doc_keys = []      # (ticker, doc_id) tuples, parallel to FAISS rows
        self.embeddings = None
        self.index = None

    @staticmethod
    def _doc_key(ticker: str, doc_file: Path):
        # doc_file stem is "doc_0123" → doc_id = 123
        return (ticker, int(doc_file.stem.split("_")[1]))

    def build_from_docs(self):
        self.docs = []
        self.doc_keys = []
        for ticker, doc_file in iter_rag_docs():
            text = doc_file.read_text()
            self.docs.append(text)
            self.doc_keys.append(self._doc_key(ticker, doc_file))

        if not self.docs:
            return

        emb = self.model.encode(self.docs, convert_to_numpy=True, show_progress_bar=False)
        self.embeddings = emb
        d = emb.shape[1]
        self.index = faiss.IndexFlatL2(d)
        self.index.add(emb)

        emb_dir = BASE / "embeddings"
        emb_dir.mkdir(parents=True, exist_ok=True)
        np.save(emb_dir / "all_docs.npy", emb)

        faiss_dir = BASE / "faiss"
        faiss_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(faiss_dir / "rag.index"))
        (faiss_dir / "docs_meta.json").write_text(
            json.dumps([{"ticker": t, "doc_id": d} for (t, d) in self.doc_keys], indent=2)
        )

    def load_from_files(self):
        emb_path = BASE / "embeddings" / "all_docs.npy"
        index_path = BASE / "faiss" / "rag.index"
        meta_path = BASE / "faiss" / "docs_meta.json"
        if not (emb_path.exists() and index_path.exists() and meta_path.exists()):
            return
        self.embeddings = np.load(emb_path)
        self.index = faiss.read_index(str(index_path))
        meta = json.loads(meta_path.read_text())
        self.doc_keys = [(m["ticker"], m["doc_id"]) for m in meta]

        self.docs = []
        for ticker, doc_id in self.doc_keys:
            path = BASE / "rag_docs" / ticker / f"doc_{doc_id:04d}.txt"
            self.docs.append(path.read_text() if path.exists() else "")

    def retrieve(self, query: str, k: int = 5):
        """Return list of (ticker, doc_id, text, distance)."""
        if self.index is None or not self.doc_keys:
            return []
        q_emb = self.model.encode([query], convert_to_numpy=True, show_progress_bar=False)
        D, I = self.index.search(q_emb, k)
        out = []
        for idx, dist in zip(I[0], D[0]):
            if 0 <= idx < len(self.doc_keys):
                ticker, doc_id = self.doc_keys[idx]
                out.append((ticker, doc_id, self.docs[idx], float(dist)))
        return out
