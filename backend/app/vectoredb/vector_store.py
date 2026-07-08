import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, 
    MatchValue, PayloadSchemaType
)

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
load_dotenv()

class VectorStore:
    """Qdrant Vector Store using openai embeddings - Local Docker storage"""
    
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize VectorStore - SINGLETON PATTERN for Qdrant Cloud"""
        if VectorStore._initialized:
            return
            
        # Initialize OpenAI embeddings
        print("🚀 Initializing OpenAI embeddings model (SINGLETON)...")
        try:
            self.embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=os.getenv("OPENAI_API_KEY")
            )
            
            # Get dimension by testing
            test_embedding = self.embeddings.embed_query("Test")
            self.dimension = len(test_embedding)
            print(f"✅ OpenAI embeddings initialized. Dimension: {self.dimension}")
            
        except Exception as e:
            print(f"❌ Error initializing OpenAI embeddings: {e}")
            raise
        
        # Initialize Qdrant client (Cloud)
        qdrant_cloud_url = os.getenv("QDRANT_CLOUD_URL")
        qdrant_cloud_api_key = os.getenv("QDRANT_CLOUD_API_KEY")
        qdrant_cloud_port = os.getenv("QDRANT_CLOUD_PORT", "6333")
        
        print(f"🔧 Initializing Qdrant client (CLOUD)...")
        print(f"   URL: {qdrant_cloud_url}")
        print(f"   Port: {qdrant_cloud_port}")
        
        try:
            # Connect to Qdrant Cloud
            if not qdrant_cloud_url or not qdrant_cloud_api_key:
                raise ValueError("QDRANT_CLOUD_URL and QDRANT_CLOUD_API_KEY must be set")
            
            # Remove trailing slash if present and ensure proper URL format
            cloud_url = qdrant_cloud_url.rstrip('/')
            if not cloud_url.startswith('https://'):
                cloud_url = f"https://{cloud_url}"
            
            self.qdrant_client = QdrantClient(
                url=cloud_url,
                api_key=qdrant_cloud_api_key,
                port=int(qdrant_cloud_port),
                prefer_grpc=False,
                timeout=120,
                https=True
            )
            
            # Test connection
            collections = self.qdrant_client.get_collections()
            print(f"✅ Qdrant Cloud client connected successfully")
            print(f"   Existing collections: {[c.name for c in collections.collections]}")
            
        except Exception as e:
            print(f"❌ Qdrant Cloud connection failed: {e}")
            raise
        
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME")
        self.website_id: Optional[str] = None
        
        print(f"✅ Qdrant VectorStore initialized (Cloud)")
        print(f"   Collection: {self.collection_name}")
        print(f"   Storage: Qdrant Cloud ({cloud_url})")
        
        # Mark as initialized
        VectorStore._initialized = True

    def ensure_collection_exists(self, vector_size: int = None):
        """Ensure the collection exists, create if not"""
        try:
            collections = self.qdrant_client.get_collections()
            collection_exists = any(c.name == self.collection_name for c in collections.collections)
            
            if not collection_exists:
                vector_size = vector_size or self.dimension
                print(f"📁 Creating Qdrant collection: {self.collection_name}")
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=vector_size,
                        distance=Distance.COSINE
                    )
                )
                print(f"✅ Collection created: {self.collection_name}")
                
                # Create index on website_id for faster filtered searches
                try:
                    self.qdrant_client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="website_id",
                        field_schema=PayloadSchemaType.KEYWORD
                    )
                    print(f"✅ Created index on website_id field")
                except Exception as e:
                    print(f"⚠️ Could not create index: {e}")
            else:
                print(f"📁 Using existing Qdrant collection: {self.collection_name}")
                
            return True
            
        except Exception as e:
            print(f"❌ Error ensuring collection exists: {e}")
            return False

    def create_from_documents(
        self,
        documents: List[Dict[str, Any]],
        website_id: str,
        base_dir: str = "data",
    ) -> Dict[str, Any]:
        """Create vector store from documents - stores in Local Qdrant"""
        self.website_id = website_id
        
        print(f"📄 Creating vector store for website: {website_id}")
        print(f"   Documents to process: {len(documents)}")
        
        # Extract texts from documents
        texts = [doc["text"] for doc in documents]
        
        # Generate embeddings
        print(f"🎨 Generating embeddings for {len(texts)} documents...")
        vectors = self.embeddings.embed_documents(texts)
        embeddings_np = np.array(vectors).astype("float32")
        dimension = embeddings_np.shape[1]
        
        print(f"📐 Embedding dimension: {dimension}")
        print(f"🔢 Number of vectors: {len(vectors)}")
        
        # Ensure collection exists
        self.ensure_collection_exists(dimension)
        
        # Store in Qdrant Local
        self._store_in_qdrant(embeddings_np, documents, website_id)
        
        # Save config locally (metadata only, NOT embeddings)
        store_dir = os.path.join(base_dir, website_id, "vector_store")
        os.makedirs(store_dir, exist_ok=True)
        
        config = {
            "website_id": website_id,
            "dimension": dimension,
            "num_documents": len(documents),
            "embedding_model": "gpt-4o-mini",
            "vector_store": "qdrant_local_docker",
            "collection_name": self.collection_name,
            "storage_location": "qdrant_local_docker",
            "created_at": datetime.now().isoformat(),
            "qdrant_host": os.getenv("QDRANT_HOST"),
            "qdrant_port": int(os.getenv("QDRANT_PORT"))
        }
        
        with open(os.path.join(store_dir, "config.json"), "w") as f:
            json.dump(config, f, indent=2)
        
        print(f"\n✅ Vector store created successfully!")
        print(f"📊 Statistics:")
        print(f"   - Website ID: {website_id}")
        print(f"   - Documents: {len(documents)}")
        print(f"   - Vectors: {len(vectors)}")
        print(f"   - Dimension: {dimension}")
        print(f"   - Storage: Local Qdrant Docker")
        print(f"   - Collection: {self.collection_name}")
        
        return config

    def _store_in_qdrant(self, embeddings: np.ndarray, documents: List[Dict[str, Any]], website_id: str):
        """Store embeddings in local Qdrant"""
        try:
            # Prepare points with UUIDs
            points = []
            for i, (embedding, doc) in enumerate(zip(embeddings, documents)):
                # Use UUID for unique point IDs
                point_id = str(uuid.uuid4())
                
                # Prepare payload with all metadata
                payload = {
                    "text": doc["text"],
                    "website_id": website_id,
                    "document_id": str(uuid.uuid4()),
                    "created_at": datetime.now().isoformat(),
                }
                
                # Add all metadata from document
                if "metadata" in doc:
                    for key, value in doc["metadata"].items():
                        if key not in payload:
                            # Handle different types for JSON serialization
                            if isinstance(value, (str, int, float, bool, list, dict)):
                                payload[key] = value
                            else:
                                payload[key] = str(value)
                
                point = PointStruct(
                    id=point_id,
                    vector=embedding.tolist(),
                    payload=payload
                )
                points.append(point)
            
            print(f"📤 Uploading {len(points)} vectors to Qdrant...")
            
            # Upload in batches for better performance
            batch_size = 100  # Larger batch for local
            total_batches = (len(points) + batch_size - 1) // batch_size
            
            for batch_idx in range(0, len(points), batch_size):
                batch = points[batch_idx:batch_idx + batch_size]
                batch_num = batch_idx // batch_size + 1
                
                print(f"   Batch {batch_num}/{total_batches} ({len(batch)} vectors)...")
                
                try:
                    self.qdrant_client.upsert(
                        collection_name=self.collection_name,
                        points=batch,
                        wait=True
                    )
                except Exception as batch_error:
                    print(f"   ⚠️ Error on batch {batch_num}, retrying with smaller batch...")
                    # Retry with smaller batch
                    for point in batch:
                        try:
                            self.qdrant_client.upsert(
                                collection_name=self.collection_name,
                                points=[point],
                                wait=True
                            )
                        except Exception as point_error:
                            print(f"   ❌ Failed to upload point {point.id}: {point_error}")
                            raise
            
            print(f"✅ Successfully stored {len(points)} vectors in Local Qdrant")
            
            # Verify upload
            collection_info = self.qdrant_client.get_collection(self.collection_name)
            print(f"📊 Collection total points: {collection_info.points_count}")
            
        except Exception as e:
            print(f"❌ Error storing in Qdrant: {str(e)}")
            raise

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        score_threshold: float = 0.3,
        website_id: Optional[str] = None,
        source_type: Optional[str] = None,  # "website" or "upload"
    ) -> List[Dict[str, Any]]:
        """
        Search for similar content - from Local Qdrant
        """
        target_website_id = website_id or self.website_id
        
        if not target_website_id:
            print("⚠️ No website_id provided for search")
            return []

        try:
            print(f"🔍 Searching in Local Qdrant for: '{query[:50]}...'")
            print(f"   Website: {target_website_id}")
            if source_type:
                print(f"   Source type: {source_type}")
            
            # Generate query embedding
            query_vector = np.array(
                self.embeddings.embed_query(query)
            ).astype("float32").tolist()
            
            # Create filter conditions
            must_conditions = [
                FieldCondition(
                    key="website_id",
                    match=MatchValue(value=target_website_id)
                )
            ]
            
            # Add source type filter if specified
            if source_type:
                must_conditions.append(
                    FieldCondition(
                        key="source_type",
                        match=MatchValue(value=source_type)
                    )
                )
            
            search_filter = Filter(
                must=must_conditions
            )
            
            # Search with filter
            search_result = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=search_filter,
                limit=k * 2,  # Get more for better filtering
                with_payload=True,
                with_vectors=False,
                score_threshold=score_threshold
            )
            
            results = []
            for hit in search_result.points:
                similarity = hit.score
                payload = hit.payload
                
                # Extract text and metadata
                text = payload.pop("text", "")
                
                results.append({
                    "document": {"text": text, "metadata": payload},
                    "metadata": payload,
                    "similarity_score": float(similarity),
                    "text": text,
                })
            
            # Sort by similarity and limit
            results.sort(key=lambda x: x["similarity_score"], reverse=True)
            results = results[:k]
            
            print(f"✅ Found {len(results)} results")
            if results:
                print(f"   Top score: {results[0]['similarity_score']:.4f}")
            
            return results
            
        except Exception as e:
            print(f"❌ Qdrant search error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def search_website_content(
        self,
        query: str,
        website_id: str,
        k: int = 5,
        score_threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Search only website content (not uploads)"""
        return self.similarity_search(
            query=query,
            k=k,
            score_threshold=score_threshold,
            website_id=website_id,
            source_type="website"
        )
    
    def search_upload_content(
        self,
        query: str,
        website_id: str,
        k: int = 3,
        score_threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Search only uploaded content"""
        return self.similarity_search(
            query=query,
            k=k,
            score_threshold=score_threshold,
            website_id=website_id,
            source_type="upload"
        )

    def get_stats(self, website_id: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for a website or all websites"""
        target_website_id = website_id or self.website_id
        
        stats = {
            "website_id": target_website_id,
            "vector_store": "qdrant_local_docker",
            "collection_name": self.collection_name,
            "embedding_model": "gpt-4o-mini",
            "storage_location": "qdrant_local_docker",
            "qdrant_host": os.getenv("QDRANT_HOST"),
            "qdrant_port": int(os.getenv("QDRANT_PORT")),
        }
        
        try:
            if target_website_id:
                # Count points for this website
                filter_condition = Filter(
                    must=[
                        FieldCondition(
                            key="website_id",
                            match=MatchValue(value=target_website_id)
                        )
                    ]
                )
                
                count_result = self.qdrant_client.count(
                    collection_name=self.collection_name,
                    count_filter=filter_condition,
                    exact=True
                )
                
                stats["website_documents"] = count_result.count
                
                # Get breakdown by source type
                filter_website = Filter(
                    must=[
                        FieldCondition(key="website_id", match=MatchValue(value=target_website_id)),
                        FieldCondition(key="source_type", match=MatchValue(value="website"))
                    ]
                )
                website_count = self.qdrant_client.count(
                    collection_name=self.collection_name,
                    count_filter=filter_website,
                    exact=True
                )
                stats["website_chunks"] = website_count.count
                
                filter_upload = Filter(
                    must=[
                        FieldCondition(key="website_id", match=MatchValue(value=target_website_id)),
                        FieldCondition(key="source_type", match=MatchValue(value="upload"))
                    ]
                )
                upload_count = self.qdrant_client.count(
                    collection_name=self.collection_name,
                    count_filter=filter_upload,
                    exact=True
                )
                stats["upload_chunks"] = upload_count.count
            
            # Get collection info
            collection_info = self.qdrant_client.get_collection(self.collection_name)
            stats["collection_points"] = collection_info.points_count
            stats["collection_vectors"] = collection_info.vectors_count
            
            return stats
            
        except Exception as e:
            print(f"❌ Error getting stats: {e}")
            stats["error"] = str(e)
            return stats

    def delete_website_data(self, website_id: str) -> bool:
        """Delete all vectors for a specific website"""
        try:
            print(f"🗑️ Deleting all vectors for website: {website_id}")
            
            filter_condition = Filter(
                must=[
                    FieldCondition(
                        key="website_id",
                        match=MatchValue(value=website_id)
                    )
                ]
            )
            
            # Count before deletion
            count_result = self.qdrant_client.count(
                collection_name=self.collection_name,
                count_filter=filter_condition,
                exact=True
            )
            
            points_count = count_result.count
            print(f"📊 Found {points_count} vectors to delete")
            
            if points_count == 0:
                print(f"⚠️ No vectors found for website: {website_id}")
                return True
            
            # Delete by filter
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=filter_condition
            )
            
            print(f"✅ Successfully deleted {points_count} vectors for website: {website_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error deleting website data: {e}")
            return False

    def delete_document(self, document_id: str) -> bool:
        """Delete a specific document by its document_id"""
        try:
            print(f"🗑️ Deleting document: {document_id}")
            
            filter_condition = Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id)
                    )
                ]
            )
            
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=filter_condition
            )
            
            print(f"✅ Deleted document: {document_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error deleting document: {e}")
            return False

    def get_collection_info(self):
        """Get Qdrant collection information"""
        try:
            collection_info = self.qdrant_client.get_collection(self.collection_name)
            
            # Get collection config
            config = {}
            if hasattr(collection_info, 'config') and collection_info.config:
                config = {
                    "params": collection_info.config.params.dict() if collection_info.config.params else {},
                    "hnsw_config": collection_info.config.hnsw_config.dict() if collection_info.config.hnsw_config else {},
                    "optimizer_config": collection_info.config.optimizer_config.dict() if collection_info.config.optimizer_config else {},
                }
            
            return {
                "collection_name": self.collection_name,
                "status": "ok",
                "vectors_count": collection_info.vectors_count,
                "points_count": collection_info.points_count,
                "indexed_vectors_count": collection_info.indexed_vectors_count,
                "config": config,
                "storage": "local_docker",
                "host": os.getenv("QDRANT_HOST"),
                "port": int(os.getenv("QDRANT_PORT")),
            }
        except Exception as e:
            return {
                "collection_name": self.collection_name,
                "status": "error",
                "error": str(e),
                "storage": "local_docker",
            }

    def list_websites(self) -> List[str]:
        """Get list of all unique website_ids in the collection"""
        try:
            # Scroll through all points to get unique website_ids
            # Note: For large collections, this might be slow
            # Consider maintaining a separate index for websites
            website_ids = set()
            next_page_offset = None
            
            while True:
                scroll_result = self.qdrant_client.scroll(
                    collection_name=self.collection_name,
                    limit=1000,
                    offset=next_page_offset,
                    with_payload=True
                )
                
                for point in scroll_result[0]:
                    if point.payload and "website_id" in point.payload:
                        website_ids.add(point.payload["website_id"])
                
                next_page_offset = scroll_result[1]
                if next_page_offset is None:
                    break
            
            return sorted(list(website_ids))
            
        except Exception as e:
            print(f"❌ Error listing websites: {e}")
            return []

    def clear_collection(self) -> bool:
        """Clear all data from the collection (use with caution!)"""
        try:
            print(f"⚠️ Clearing entire collection: {self.collection_name}")
            confirm = input(f"Type 'DELETE' to confirm clearing all data: ")
            if confirm != "DELETE":
                print("Operation cancelled")
                return False
            
            # Delete all points
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(must=[])  # Empty filter matches all
            )
            
            print(f"✅ Collection cleared: {self.collection_name}")
            return True
            
        except Exception as e:
            print(f"❌ Error clearing collection: {e}")
            return False

    def test_connection(self) -> Dict[str, Any]:
        """Test connection to Qdrant"""
        try:
            # Test basic connection
            collections = self.qdrant_client.get_collections()
            
            # Test embedding generation
            test_embedding = self.embeddings.embed_query("Test connection")
            
            return {
                "success": True,
                "qdrant_connected": True,
                "embeddings_working": True,
                "dimension": len(test_embedding),
                "collections": [c.name for c in collections.collections],
                "collection_exists": any(c.name == self.collection_name for c in collections.collections),
                "storage": "local_docker",
                "host": os.getenv("QDRANT_HOST"),
                "port": int(os.getenv("QDRANT_PORT")),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "storage": "local_docker",
            }