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
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv
from app.tokens.token_counter import token_counter

load_dotenv()

class EmbeddingHandler:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize OpenAI embedding model and Qdrant client - SINGLETON PATTERN"""
        if EmbeddingHandler._initialized:
            return
            
        # Initialize OpenAI embeddings
        print("🚀 Initializing OpenAI embeddings model (SINGLETON)...")
        try:
            self.embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=os.getenv("OPENAI_API_KEY")
            )
            
            test_embedding = self.embeddings.embed_query("Test query")
            self.dimension = len(test_embedding)
            print(f"✅ OpenAI embeddings initialized. Dimension: {self.dimension}")
            
        except Exception as e:
            print(f"❌ Error initializing OpenAI embeddings: {e}")
            raise

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""],
        )
        
        # Initialize Qdrant client (Cloud)
        qdrant_cloud_url = os.getenv("QDRANT_CLOUD_URL")
        qdrant_cloud_api_key = os.getenv("QDRANT_CLOUD_API_KEY")
        qdrant_cloud_port = os.getenv("QDRANT_CLOUD_PORT", "6333")
        
        print(f"🔧 Initializing Qdrant client (CLOUD)...")
        print(f"   URL: {qdrant_cloud_url}")
        print(f"   Port: {qdrant_cloud_port}")
        
        # For Qdrant Cloud, always use HTTPS and API key
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
            prefer_grpc=False,  # Use HTTP for cloud (more stable with some networks)
            timeout=120,
            https=True  # Explicitly use HTTPS for cloud
        )
        
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME")
        
        # Test connection
        try:
            collections = self.qdrant_client.get_collections()
            print(f"✅ Qdrant Cloud connected successfully")
            print(f"   Existing collections: {[c.name for c in collections.collections]}")
        except Exception as e:
            print(f"❌ Qdrant Cloud connection failed: {e}")
            raise
        
        print(f"✅ Qdrant EmbeddingHandler initialized (Cloud)")
        
        EmbeddingHandler._initialized = True

    def ensure_index_exists(self):
        """Ensure that the website_id index exists in the collection"""
        try:
            collections = self.qdrant_client.get_collections()
            collection_exists = any(c.name == self.collection_name for c in collections.collections)
            
            if not collection_exists:
                print(f"📁 Collection {self.collection_name} does not exist yet")
                return False
            
            try:
                self.qdrant_client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="website_id",
                    field_schema=PayloadSchemaType.KEYWORD
                )
                print(f"✅ Created index on website_id field")
                return True
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"✅ Index on website_id already exists")
                    return True
                else:
                    print(f"⚠️ Could not create index: {e}")
                    return False
                    
        except Exception as e:
            print(f"❌ Error ensuring index exists: {e}")
            return False

    def check_embeddings_exist(self, website_id: str) -> bool:
        """Check if embeddings exist for a website in Qdrant"""
        try:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="website_id",
                        match=MatchValue(value=website_id)
                    )
                ]
            )
            
            count_result = self.qdrant_client.count(
                collection_name=self.collection_name,
                count_filter=search_filter,
                exact=True
            )
            
            has_embeddings = count_result.count > 0
            print(f"📊 Found {count_result.count} embeddings for website {website_id} in Qdrant")
            return has_embeddings
                
        except Exception as e:
            print(f"❌ Error checking embeddings in Qdrant: {e}")
            return False

    def create_embeddings(
        self,
        website_id: str,
        website_data: List[Dict[str, Any]],
        base_dir: str = "data",
        include_uploads: bool = True,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create embeddings from website data - store in Local Qdrant"""
        website_dir = os.path.join(base_dir, website_id)
        os.makedirs(website_dir, exist_ok=True)

        documents = []
        
        print(f"📄 Processing {len(website_data)} website data items...")
        
        for i, page in enumerate(website_data):
            try:
                print(f"\n📑 Processing page {i+1}/{len(website_data)}")
                
                content = ""
                metadata = {}
                
                if isinstance(page, dict):
                    if "content" in page:
                        content = page["content"]
                    elif "text" in page:
                        content = page["text"]
                    elif "Content" in page:
                        content = page["Content"]
                    elif "body" in page:
                        content = page["body"]
                    else:
                        for key, value in page.items():
                            if isinstance(value, str) and len(value) > 100 and key not in ['metadata', 'url', 'title']:
                                content = value
                                break
                    
                    if not content and isinstance(page, tuple) and len(page) >= 2:
                        content = page[1] if len(page) > 1 else ""
                    
                    if "metadata" in page and isinstance(page["metadata"], dict):
                        metadata.update(page["metadata"])
                    
                    for key, value in page.items():
                        if key not in ["content", "text", "Content", "body", "metadata"]:
                            if isinstance(value, (str, int, float)):
                                metadata[key] = value
                
                if content and not isinstance(content, str):
                    try:
                        content = str(content)
                    except:
                        content = ""
                
                if not content or len(content.strip()) < 50:
                    print(f"⚠️ Skipping page {i+1}: No sufficient content (len={len(content) if content else 0})")
                    continue
                
                chunks = self.text_splitter.split_text(content)
                print(f"📝 Split into {len(chunks)} chunks")
                
                for chunk_idx, chunk in enumerate(chunks):
                    if not chunk.strip():
                        continue
                        
                    doc_metadata = metadata.copy()
                    
                    title = ""
                    if isinstance(page, dict):
                        title = page.get("title", "")
                        if not title and "metadata" in page and isinstance(page["metadata"], dict):
                            title = page["metadata"].get("title", "")
                    
                    doc_metadata.setdefault("title", title or f"Page {i+1}")
                    doc_metadata.setdefault("url", page.get("url", "") if isinstance(page, dict) else "")
                    doc_metadata.setdefault("source_type", "website")
                    doc_metadata.setdefault("website_id", website_id)
                    doc_metadata.setdefault("page_index", i)
                    doc_metadata.setdefault("chunk_index", chunk_idx)
                    doc_metadata.setdefault("total_chunks", len(chunks))
                    doc_metadata.setdefault("document_id", str(uuid.uuid4()))
                    
                    if isinstance(page, dict) and "metadata" in page and isinstance(page["metadata"], dict):
                        if "extraction_method" in page["metadata"]:
                            doc_metadata["extraction_method"] = page["metadata"]["extraction_method"]
                    
                    documents.append({
                        "text": chunk,
                        "metadata": doc_metadata
                    })
                    
            except Exception as e:
                print(f"❌ Error processing page {i+1}: {e}")
                import traceback
                traceback.print_exc()
                continue

        print(f"✅ Created {len(documents)} total chunks from website content")

        upload_docs_count = 0
        if include_uploads:
            uploads_docs = self._load_uploaded_documents(website_id, base_dir)
            upload_docs_count = len(uploads_docs)
            documents.extend(uploads_docs)
            print(f"📎 Added {upload_docs_count} upload chunks")

        if not documents:
            raise ValueError("No documents to embed")

        debug_file = os.path.join(website_dir, "embedding_debug.json")
        try:
            with open(debug_file, 'w', encoding='utf-8') as f:
                debug_data = []
                for doc in documents[:10]:
                    debug_data.append({
                        "text_preview": doc["text"][:200] + "..." if len(doc["text"]) > 200 else doc["text"],
                        "metadata": doc["metadata"],
                        "text_length": len(doc["text"])
                    })
                json.dump(debug_data, f, indent=2, ensure_ascii=False)
            print(f"💾 Saved debug info to {debug_file}")
        except Exception as e:
            print(f"⚠️ Could not save debug file: {e}")

        texts = [doc["text"] for doc in documents]
        
        print(f"\n🎨 Creating embeddings with OpenAI for {len(texts)} total chunks...")
        
        token_data = token_counter.track_embedding_tokens(
            website_id=website_id,
            user_id=user_id,
            texts=texts,
            model="text-embedding-3-small",
            operation_type="training",
            metadata={'document_count': len(documents)}
        )
        
        print(f"📊 Embedding token usage: {token_data['embedding_tokens']} tokens")
        
        try:
            print("🔄 Generating embeddings with OpenAI")
            vectors = self.embeddings.embed_documents(texts)
            embeddings_np = np.array(vectors).astype("float32")
            
            dimension = embeddings_np.shape[1]
            print(f"📐 Embedding dimension: {dimension}")
            print(f"🔢 Number of vectors: {len(vectors)}")
            
            self._store_in_qdrant(website_id, embeddings_np, documents)
            
            info = {
                "website_id": website_id,
                "num_chunks": len(documents),
                "num_vectors": len(vectors),
                "embedding_dimension": dimension,
                "embedding_model": "text-embedding-3-small",
                "vector_store": "qdrant_local_docker",
                "collection_name": self.collection_name,
                "created_at": datetime.now().isoformat(),
                "includes_uploads": include_uploads,
                "upload_count": upload_docs_count,
                "website_chunks": len(documents) - upload_docs_count,
                "storage_location": "qdrant_local_docker",
                "embedding_tokens": token_data['embedding_tokens']
            }

            with open(os.path.join(website_dir, "info.json"), "w") as f:
                json.dump(info, f, indent=2)

            print(f"\n✅ Embeddings created successfully and stored in Local Qdrant Docker!")
            print(f"📊 Total chunks: {len(documents)}")
            print(f"🔢 Total vectors: {len(vectors)}")
            print(f"🗄️ Qdrant collection: {self.collection_name}")
            print(f"📍 Storage: Local Qdrant Docker")
            
            return info
            
        except Exception as e:
            print(f"❌ Error creating embeddings: {str(e)}")
            import traceback
            traceback.print_exc()
            
            error_file = os.path.join(website_dir, "embedding_error.json")
            with open(error_file, 'w') as f:
                json.dump({
                    "error": str(e),
                    "document_count": len(documents),
                    "timestamp": datetime.now().isoformat()
                }, f, indent=2)
            
            raise

    def _store_in_qdrant(self, website_id: str, embeddings: np.ndarray, documents: List[Dict[str, Any]]):
        """Store embeddings in local Qdrant collection"""
        try:
            collections = self.qdrant_client.get_collections()
            collection_exists = False
            for collection in collections.collections:
                if collection.name == self.collection_name:
                    collection_exists = True
                    break
            
            if not collection_exists:
                print(f"📁 Creating new Qdrant collection: {self.collection_name}")
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=embeddings.shape[1],
                        distance=Distance.COSINE
                    )
                )
                print(f"✅ Collection created: {self.collection_name}")
                
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
                self.ensure_index_exists()
            
            points = []
            for i, (embedding, doc) in enumerate(zip(embeddings, documents)):
                point_id = str(uuid.uuid4())  # Use UUID for unique IDs
                
                payload = {
                    "text": doc["text"],
                    "website_id": website_id,
                    "document_id": doc["metadata"].get("document_id", str(uuid.uuid4())),
                    **doc["metadata"]
                }
                
                point = PointStruct(
                    id=point_id,
                    vector=embedding.tolist(),
                    payload=payload
                )
                points.append(point)
            
            print(f"📤 Preparing to upload {len(points)} vectors to Qdrant...")
            
            batch_size = 100  # Larger batch for local
            total_batches = (len(points) - 1) // batch_size + 1
            
            for batch_idx in range(0, len(points), batch_size):
                batch = points[batch_idx:batch_idx + batch_size]
                batch_num = batch_idx // batch_size + 1
                
                print(f"⬆️ Uploading batch {batch_num}/{total_batches} ({len(batch)} vectors)...")
                
                try:
                    self.qdrant_client.upsert(
                        collection_name=self.collection_name,
                        points=batch,
                        wait=True
                    )
                    print(f"✅ Batch {batch_num}/{total_batches} uploaded successfully")
                except Exception as batch_error:
                    print(f"❌ Error uploading batch {batch_num}: {batch_error}")
                    if batch_size > 10:
                        batch_size = max(10, batch_size // 2)
                        print(f"🔄 Reducing batch size to {batch_size}")
                        continue
                    else:
                        raise
            
            print(f"✅ Successfully stored {len(points)} vectors in Qdrant")
            
            try:
                collection_info = self.qdrant_client.get_collection(self.collection_name)
                print(f"📊 Collection stats: {collection_info.points_count} total points")
            except Exception as e:
                print(f"⚠️ Could not verify collection stats: {e}")
            
        except Exception as e:
            print(f"❌ Error storing in Qdrant: {str(e)}")
            raise

    def _load_uploaded_documents(self, website_id: str, base_dir: str) -> List[Dict[str, Any]]:
        """Load processed documents from uploaded files"""
        upload_dir = os.path.join(base_dir, website_id, "uploads")
        if not os.path.exists(upload_dir):
            return []

        documents = []
        
        uploads_meta = os.path.join(upload_dir, "uploads_metadata.json")
        if os.path.exists(uploads_meta):
            try:
                with open(uploads_meta, 'r', encoding='utf-8') as f:
                    uploads_data = json.load(f)
                
                for upload in uploads_data:
                    if upload.get('processed', False):
                        processed_file = os.path.join(upload_dir, 
                                                     f"{upload['saved_filename']}_processed.json")
                        if os.path.exists(processed_file):
                            with open(processed_file, 'r', encoding='utf-8') as f:
                                file_docs = json.load(f)
                            
                            for doc in file_docs:
                                if isinstance(doc, dict) and "text" in doc:
                                    doc_metadata = doc.get("metadata", {})
                                    doc_metadata["source_type"] = 'upload'
                                    doc_metadata["upload_filename"] = upload['original_filename']
                                    doc_metadata["uploaded_at"] = upload.get('uploaded_at', '')
                                    doc_metadata["website_id"] = website_id
                                    doc_metadata["document_id"] = str(uuid.uuid4())
                                    
                                    documents.append({
                                        "text": doc["text"],
                                        "metadata": doc_metadata
                                    })
                                
            except Exception as e:
                print(f"❌ Error loading uploaded documents: {e}")
        
        return documents

    def search_similar_content(
        self,
        website_id: str,
        query: str,
        top_k: int = 5,
        search_uploads: bool = True,
        score_threshold: float = 0.1
    ) -> List[Dict[str, Any]]:
        """Search for similar content - from Local Qdrant"""
        try:
            print(f"🔍 Searching in Local Qdrant for: '{query[:50]}...' in website: {website_id}")
            
            query_vector = np.array(
                self.embeddings.embed_query(query)
            ).astype("float32").tolist()
            
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="website_id",
                        match=MatchValue(value=website_id)
                    )
                ]
            )
            
            search_result = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=search_filter,
                limit=top_k * 3,
                with_payload=True,
                with_vectors=False,
                score_threshold=score_threshold
            )
            
            results = []
            for hit in search_result.points:
                payload = hit.payload
                similarity = hit.score
                
                if not search_uploads:
                    source_type = payload.get("source_type", "website")
                    if source_type != "website":
                        continue
                
                results.append({
                    "text": payload.get("text", ""),
                    "metadata": {k: v for k, v in payload.items() if k != "text"},
                    "similarity_score": float(similarity),
                })
            
            print(f"✅ Found {len(results)} results")
            results.sort(key=lambda x: x["similarity_score"], reverse=True)
            return results[:top_k]
            
        except Exception as e:
            print(f"❌ Error searching embeddings in Qdrant: {e}")
            import traceback
            traceback.print_exc()
            return []

    def search_uploaded_content(
        self,
        website_id: str,
        query: str,
        top_k: int = 3,
        score_threshold: float = 0.1
    ) -> List[Dict[str, Any]]:
        """Specifically search uploaded files - from Local Qdrant"""
        try:
            print(f"🔍 Searching uploaded content in Qdrant for: '{query[:50]}...'")
            
            query_vector = np.array(
                self.embeddings.embed_query(query)
            ).astype("float32").tolist()
            
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="website_id",
                        match=MatchValue(value=website_id)
                    ),
                    FieldCondition(
                        key="source_type",
                        match=MatchValue(value="upload")
                    )
                ]
            )
            
            search_result = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=search_filter,
                limit=top_k * 2,
                with_payload=True,
                with_vectors=False,
                score_threshold=score_threshold
            )
            
            results = []
            for hit in search_result.points:
                payload = hit.payload
                similarity = hit.score
                
                results.append({
                    "text": payload.get("text", ""),
                    "metadata": {k: v for k, v in payload.items() if k != "text"},
                    "similarity_score": float(similarity),
                })
            
            print(f"✅ Found {len(results)} upload results")
            return results[:top_k]
            
        except Exception as e:
            print(f"❌ Error searching uploaded content: {e}")
            return []

    def get_document_stats(self, website_id: str) -> Dict[str, Any]:
        """Get statistics about documents in Qdrant"""
        try:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="website_id",
                        match=MatchValue(value=website_id)
                    )
                ]
            )
            
            count_result = self.qdrant_client.count(
                collection_name=self.collection_name,
                count_filter=search_filter,
                exact=True
            )
            total_documents = count_result.count
            
            stats = {
                "total_documents": total_documents,
                "website_documents": 0,
                "upload_documents": 0,
                "document_types": {},
                "file_types": {},
                "vector_store": "qdrant_local_docker",
                "collection_name": self.collection_name,
                "storage_location": "qdrant_local_docker"
            }
            
            scroll_result = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                filter=search_filter,
                limit=1000,
                with_payload=True
            )
            
            for point in scroll_result[0]:
                payload = point.payload
                source_type = payload.get("source_type", "website")
                
                if source_type == "website":
                    stats["website_documents"] += 1
                    doc_type = payload.get("type", "unknown")
                    stats["document_types"][doc_type] = stats["document_types"].get(doc_type, 0) + 1
                else:
                    stats["upload_documents"] += 1
                    file_type = payload.get("type", "unknown")
                    stats["file_types"][file_type] = stats["file_types"].get(file_type, 0) + 1
            
            return stats
            
        except Exception as e:
            print(f"❌ Error getting document stats: {e}")
            return {"error": str(e), "vector_store": "qdrant_local_docker"}

    def delete_website_embeddings(self, website_id: str) -> bool:
        """Delete all embeddings for a website from Qdrant"""
        try:
            print(f"🗑️ Attempting to delete embeddings for website: {website_id}")
            
            filter_condition = Filter(
                must=[
                    FieldCondition(
                        key="website_id",
                        match=MatchValue(value=website_id)
                    )
                ]
            )
            
            count_result = self.qdrant_client.count(
                collection_name=self.collection_name,
                count_filter=filter_condition,
                exact=True
            )
            
            points_count = count_result.count
            print(f"📊 Found {points_count} points to delete for website: {website_id}")
            
            if points_count == 0:
                print(f"⚠️ No embeddings found for website: {website_id}")
                return True
            
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=filter_condition
            )
            
            print(f"✅ Successfully deleted {points_count} embeddings for website: {website_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error deleting website embeddings from Qdrant: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_collection_stats(self):
        """Get Qdrant collection statistics"""
        try:
            collection_info = self.qdrant_client.get_collection(self.collection_name)
            return {
                "collection_name": self.collection_name,
                "vectors_count": collection_info.vectors_count,
                "points_count": collection_info.points_count,
                "indexed_vectors_count": collection_info.indexed_vectors_count,
                "status": "ok",
                "storage": "local_docker"
            }
        except Exception as e:
            return {
                "error": str(e),
                "collection_name": self.collection_name,
                "status": "error",
                "storage": "local_docker"
            }

    def test_qdrant_connection(self):
        """Test Qdrant connection and basic operations"""
        try:
            collections = self.qdrant_client.get_collections()
            print(f"✅ Qdrant connection successful")
            print(f"📁 Available collections: {[c.name for c in collections.collections]}")
            
            collection_exists = any(c.name == self.collection_name for c in collections.collections)
            
            if collection_exists:
                print(f"✅ Collection '{self.collection_name}' exists")
                collection_info = self.qdrant_client.get_collection(self.collection_name)
                print(f"📊 Collection stats: {collection_info.points_count} points")
                self.ensure_index_exists()
                
                try:
                    test_vector = [0.1] * self.dimension
                    test_result = self.qdrant_client.query_points(
                        collection_name=self.collection_name,
                        query=test_vector,
                        limit=1,
                        with_payload=False
                    )
                    print(f"✅ Search test successful")
                except Exception as search_error:
                    print(f"⚠️ Search test failed: {search_error}")
            else:
                print(f"⚠️ Collection '{self.collection_name}' does not exist")
            
            return {
                "success": True,
                "connection": "ok",
                "collection_exists": collection_exists,
                "collection_name": self.collection_name,
                "dimension": self.dimension,
                "storage": "local_docker"
            }
            
        except Exception as e:
            print(f"❌ Qdrant connection failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "connection": "failed",
                "storage": "local_docker"
            }