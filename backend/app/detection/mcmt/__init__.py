"""
Multi-Camera Multi-Target (MCMT) Tracking System

Architecture:
1. EmbeddingExtractor - Extracts OSNet appearance embeddings from YOLO detection crops
2. EmbeddingGallery - FAISS vector store for sub-millisecond cross-camera similarity search
3. GlobalTracker - Assigns persistent global IDs across all cameras using embeddings + spatial-temporal constraints
"""
