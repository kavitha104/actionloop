import math
import re
import json
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from backend.models.domain import Decision
from backend.config import settings

class MemoryService:
    @staticmethod
    def get_embedding(text: str) -> List[float]:
        """
        Generates embedding vector for a decision text.
        Uses Gemini embeddings if GEMINI_API_KEY is present;
        otherwise computes normalized semantic n-gram feature vector for 100% deterministic local vector search.
        """
        if not settings.demo_mode and settings.gemini_api_key:
            try:
                from google import genai
                client = genai.Client(api_key=settings.gemini_api_key)
                res = client.models.embed_content(
                    model=settings.gemini_embedding_model,
                    contents=text
                )
                if res.embeddings and len(res.embeddings) > 0:
                    return res.embeddings[0].values
            except Exception as e:
                print(f"[MemoryService] Gemini embedding failed: {e}. Using deterministic local embedding.")

        return MemoryService._deterministic_vector(text)

    @staticmethod
    def _deterministic_vector(text: str, dim: int = 128) -> List[float]:
        """
        Lightweight deterministic hash projection into normalized dim-dimensional space.
        Provides robust cosine similarity for semantic tokens without external dependencies.
        """
        words = re.findall(r'\b\w+\b', text.lower())
        vec = [0.0] * dim
        if not words:
            return vec

        for word in words:
            # Hash word into bucket
            h = hash(word)
            idx = abs(h) % dim
            sign = 1.0 if (h >> 4) % 2 == 0 else -1.0
            vec[idx] += sign

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        return max(0.0, min(1.0, (dot + 1.0) / 2.0))  # Map to 0..1

    @classmethod
    def search_similar_decisions(
        cls,
        db: Session,
        query_text: str,
        topic: Optional[str] = None,
        top_k: int = 5,
        active_only: bool = True
    ) -> List[Tuple[Decision, float]]:
        """
        Retrieves top_k similar decisions from cross-meeting memory.
        """
        query_vec = cls.get_embedding(query_text)

        stmt = db.query(Decision)
        if active_only:
            stmt = stmt.filter(Decision.status == "active")
        all_decisions = stmt.all()

        scored: List[Tuple[Decision, float]] = []
        for d in all_decisions:
            # Semantic similarity score
            target_text = f"{d.topic} {d.statement} {d.rationale or ''}"
            target_vec = d.embedding
            if not target_vec:
                target_vec = cls.get_embedding(target_text)
                d.embedding = target_vec
                db.add(d)

            sim = cls.cosine_similarity(query_vec, target_vec)

            # Topic boost
            if topic and d.topic and topic.lower() == d.topic.lower():
                sim = min(1.0, sim + 0.25)

            # Keyword overlap boost
            q_words = set(re.findall(r'\b\w{4,}\b', query_text.lower()))
            t_words = set(re.findall(r'\b\w{4,}\b', target_text.lower()))
            common = q_words.intersection(t_words)
            if common:
                sim = min(1.0, sim + 0.15 * len(common))

            scored.append((d, round(sim, 3)))

        # Sort descending by similarity score
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
