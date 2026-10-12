"""
tools/algorithms/rag_engine.py
Moteur RAG (Retrieval-Augmented Generation) optimisé (Numpy)
"""

import math
import re
import json
import os
from collections import Counter
from typing import List, Dict, Any, Optional
import numpy as np

class RAGEngine:
    def __init__(self, kb_path: str = "memory/knowledge_base.json"):
        self.kb_path = kb_path
        self.documents: List[Dict[str, Any]] = []
        self._vocab: Dict[str, int] = {}
        self._idf: Optional[np.ndarray] = None
        self._doc_vectors: Optional[np.ndarray] = None
        self._doc_lengths: Optional[np.ndarray] = None
        self._avg_dl = 0.0
        self.load_knowledge_base()

    def load_knowledge_base(self) -> None:
        if os.path.exists(self.kb_path):
            try:
                with open(self.kb_path, "r", encoding="utf-8") as f:
                    self.documents = json.load(f)
                    self._build_index()
            except Exception as e:
                print(f"[RAGEngine] Erreur chargement KB: {e}")
                self.documents = []
        else:
            self.documents = []

    def save_knowledge_base(self) -> None:
        os.makedirs(os.path.dirname(self.kb_path), exist_ok=True)
        with open(self.kb_path, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, ensure_ascii=False, indent=2)
        self._build_index()

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r'\w+', text.lower())

    def _build_index(self) -> None:
        """Construit les matrices Numpy pour des calculs BM25/TF-IDF quasi-instantanés."""
        if not self.documents:
            return
            
        vocab_set = set()
        tokenized_docs = []
        for doc in self.documents:
            tokens = self._tokenize(doc.get("text", ""))
            tokenized_docs.append(tokens)
            vocab_set.update(tokens)
            
        self._vocab = {word: idx for idx, word in enumerate(vocab_set)}
        vocab_size = len(self._vocab)
        num_docs = len(self.documents)
        
        tf_matrix = np.zeros((num_docs, vocab_size), dtype=np.float32)
        self._doc_lengths = np.zeros(num_docs, dtype=np.float32)
        
        for i, tokens in enumerate(tokenized_docs):
            self._doc_lengths[i] = len(tokens)
            counts = Counter(tokens)
            for word, count in counts.items():
                idx = self._vocab[word]
                tf_matrix[i, idx] = count
                
        doc_freqs = np.sum(tf_matrix > 0, axis=0)
        self._idf = np.log((num_docs - doc_freqs + 0.5) / (doc_freqs + 0.5) + 1.0)
        self._doc_vectors = tf_matrix
        self._avg_dl = np.mean(self._doc_lengths) if num_docs > 0 else 0.0

    def compute_tfidf_score(self, query: str, doc_text: str) -> float:
        """Fallback sur une approche scalaire si besoin."""
        q_tokens = self._tokenize(query)
        d_tokens = self._tokenize(doc_text)
        if not q_tokens or not d_tokens:
            return 0.0
        
        d_counts = Counter(d_tokens)
        doc_len = len(d_tokens)
        score = 0.0
        
        for qt in set(q_tokens):
            tf = d_counts[qt] / doc_len
            if tf > 0:
                score += tf * (1.0 + math.log(1 + q_tokens.count(qt)))
        return score

    def bm25_retrieve(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Implémentation BM25 entièrement vectorisée via Numpy."""
        if not self.documents or self._doc_vectors is None:
            return []
            
        q_tokens = self._tokenize(query)
        q_indices = [self._vocab[qt] for qt in q_tokens if qt in self._vocab]
        
        if not q_indices:
            return []
            
        k1 = 1.5
        b = 0.75
        
        tf_query_terms = self._doc_vectors[:, q_indices]
        idf_query_terms = self._idf[q_indices]
        
        len_norm = self._doc_lengths / (self._avg_dl + 1e-5)
        denominator = tf_query_terms + k1 * (1 - b + b * len_norm[:, np.newaxis])
        numerator = tf_query_terms * (k1 + 1)
        
        scores = np.sum(idf_query_terms * (numerator / (denominator + 1e-5)), axis=1)
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append(self.documents[idx])
                
        return results

    def semantic_chunker(self, text: str, chunk_size: int = 200, overlap: int = 50) -> List[str]:
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for p in paragraphs:
            if len(current_chunk) + len(p) <= chunk_size:
                current_chunk += p + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = p + "\n\n"
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks

    def inject_rag_context(self, prompt: str, retrieved_docs: List[Dict[str, Any]]) -> str:
        if not retrieved_docs:
            return prompt
        
        context_str = "\n".join([f"--- Doc {i+1} ---\n{d.get('text', '')}" for i, d in enumerate(retrieved_docs)])
        return f"[CONTEXTE DOCUMENTAIRE PERTINENT]\n{context_str}\n\n[QUESTION]\n{prompt}"

    def add_document(self, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.documents.append({
            "id": doc_id,
            "text": text,
            "metadata": metadata or {}
        })
        self.save_knowledge_base()

    def auto_index_directory(self, dir_path: str, extensions: List[str] = [".txt", ".md", ".json"]) -> int:
        if not os.path.exists(dir_path):
            return 0
        indexed_count = 0
        for root, _, files in os.walk(dir_path):
            for file in files:
                if any(file.endswith(ext) for ext in extensions):
                    full_path = os.path.join(root, file)
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            if content.strip():
                                self.add_document(doc_id=file, text=content[:2000], metadata={"path": full_path})
                                indexed_count += 1
                    except Exception:
                        pass
        return indexed_count

    def score_relevance(self, query: str, chunk: str) -> float:
        return self.compute_tfidf_score(query, chunk)

    def hybrid_search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        return self.bm25_retrieve(query, top_k=top_k)

    def expand_query(self, query: str) -> List[str]:
        synonyms = {
            "erreur": ["bug", "exception", "crash", "faute"],
            "code": ["script", "fonction", "programme", "python"],
            "mémoire": ["historique", "context", "souvenir", "ltm"]
        }
        words = self._tokenize(query)
        expanded = set(words)
        for w in words:
            if w in synonyms:
                expanded.update(synonyms[w])
        return list(expanded)

    def deduplicate_results(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_texts = set()
        unique_docs = []
        for d in docs:
            txt = d.get("text", "").strip()
            if txt not in seen_texts:
                seen_texts.add(txt)
                unique_docs.append(d)
        return unique_docs
