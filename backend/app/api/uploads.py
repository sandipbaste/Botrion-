from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from typing import List, Dict, Any, Optional
from datetime import datetime
import os
import json
import uuid
import aiofiles
import shutil

from app.database.database import db_manager
from app.file_processor import FileProcessor
from app.vectoredb.embedding_handler import EmbeddingHandler
from .auth import get_current_user

router = APIRouter()



@router.post("/{website_id}")
async def upload_files(
    website_id: str,
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = None,
    user: dict = Depends(get_current_user)
):
    """Upload additional files to existing website"""
    try:
        print(f" Upload request for website: {website_id}")
        print(f" Files type: {type(files)}")
        print(f" Files: {files}")
        
        # Handle different file formats
        valid_files = []
        
        if isinstance(files, list):
            for file in files:
                if hasattr(file, 'filename') and hasattr(file, 'read'):
                    valid_files.append(file)
                elif isinstance(file, bytes):
                    # Convert bytes to UploadFile
                    from fastapi import UploadFile
                    import io
                    file_obj = io.BytesIO(file)
                    valid_files.append(UploadFile(file=file_obj, filename="uploaded_file"))
                else:
                    print(f"  Skipping invalid file: {type(file)}")
        elif hasattr(files, 'filename') and hasattr(files, 'read'):
            valid_files = [files]
        elif isinstance(files, bytes):
            # Single bytes file
            from fastapi import UploadFile
            import io
            file_obj = io.BytesIO(files)
            valid_files = [UploadFile(file=file_obj, filename="uploaded_file")]
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "Invalid file format",
                    "message": "Please upload files as multipart/form-data"
                }
            )
        
        if not valid_files:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "No valid files",
                    "message": "No valid files found. Please ensure files are properly selected."
                }
            )
        
        files = valid_files
        print(f" Processing {len(files)} valid files: {[f.filename for f in files]}")
        
        # Check website exists
        website = db_manager.get_website(website_id)
        if not website:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Website not found",
                    "message": f"Website with ID {website_id} not found."
                }
            )
        
        # Check permission
        if website.get('user_id') != user['id'] and user.get('role') != 'admin':
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "error": "Permission denied",
                    "message": "You don't have permission to upload files to this website."
                }
            )
        
        # Create directories
        website_dir = os.path.join("data", website_id)
        upload_dir = os.path.join(website_dir, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        uploaded_files = []
        successful_uploads = 0
        failed_uploads = 0
        file_processor = FileProcessor()
        
        for file in files:
            try:
                # Validate file
                if not file.filename:
                    continue
                
                # Generate safe filename
                safe_filename = "".join(c for c in file.filename if c.isalnum() or c in ('.', '-', '_')).rstrip()
                if not safe_filename:
                    safe_filename = f"file_{uuid.uuid4().hex[:8]}"
                
                file_path = os.path.join(upload_dir, safe_filename)
                
                # Read file content
                content = await file.read()
                
                if not content:
                    print(f"  Warning: {file.filename} is empty")
                    failed_uploads += 1
                    continue
                
                # Save file
                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(content)
                
                # Process file
                try:
                    processed_content = file_processor.process_file(file_path)
                    processed = True
                    chunks = len(processed_content)
                    
                    processed_file = os.path.join(upload_dir, f"{safe_filename}_processed.json")
                    with open(processed_file, 'w', encoding='utf-8') as f:
                        json.dump(processed_content, f, ensure_ascii=False, indent=2)
                    
                except Exception as e:
                    print(f" Error processing {file.filename}: {e}")
                    processed = False
                    chunks = 0
                    failed_uploads += 1
                
                if processed:
                    successful_uploads += 1
                
                # Save file record to database
                file_data = {
                    'filename': safe_filename,
                    'file_path': file_path,
                    'file_type': os.path.splitext(safe_filename)[1][1:] if '.' in safe_filename else 'unknown',
                    'file_size': len(content),
                    'upload_type': 'user_upload',
                    'processed': processed,
                    'chunk_count': chunks
                }
                db_manager.save_file_record(website_id, file_data)
                
                uploaded_files.append({
                    "original_filename": file.filename,
                    "saved_filename": safe_filename,
                    "size": len(content),
                    "saved_path": file_path,
                    "processed": processed,
                    "chunks": chunks,
                    "uploaded_at": datetime.now().isoformat(),
                    "success": processed
                })
                
                print(f" Uploaded: {file.filename} -> {safe_filename} ({len(content)} bytes, processed: {processed})")
                
            except Exception as e:
                print(f"  Error uploading {file.filename}: {e}")
                failed_uploads += 1
                uploaded_files.append({
                    "original_filename": file.filename if hasattr(file, 'filename') else 'Unknown',
                    "error": str(e),
                    "processed": False,
                    "success": False
                })
        
        # Save uploads metadata
        uploads_meta = os.path.join(upload_dir, "uploads_metadata.json")
        try:
            existing_uploads = []
            if os.path.exists(uploads_meta):
                with open(uploads_meta, 'r', encoding='utf-8') as f:
                    existing_uploads = json.load(f)
            
            all_uploads = existing_uploads + uploaded_files
            
            with open(uploads_meta, 'w', encoding='utf-8') as f:
                json.dump(all_uploads, f, ensure_ascii=False, indent=2)
            
            print(f"Saved uploads metadata for {website_id}")
            
        except Exception as e:
            print(f" Warning: Could not save uploads metadata: {e}")
        
        # Start reindexing in background if files were uploaded successfully
        if successful_uploads > 0:
            if background_tasks:
                background_tasks.add_task(reindex_with_uploads, website_id)
                print(f"✅ Reindexing task added for website: {website_id}")
            else:
                # If no background_tasks, run synchronously
                print(f"⚠️ No background_tasks, running reindex synchronously...")
                await reindex_with_uploads(website_id)
        
        return {
            "success": True,
            "message": message,
            "website_id": website_id,
            "uploaded_files": uploaded_files,
            "total_files": len(files),
            "successful_uploads": successful_uploads,
            "failed_uploads": failed_uploads,
            "upload_dir": upload_dir,
            "reindexing": successful_uploads > 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"  Upload error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Upload failed",
                "message": str(e)
            }
        )


async def reindex_with_uploads(website_id: str):
    """Reindex embeddings to include uploaded files"""
    try:
        print(f" Starting reindex for website: {website_id}")
        
        website_dir = os.path.join("data", website_id)
        upload_dir = os.path.join(website_dir, "uploads")
        
        if not os.path.exists(upload_dir):
            print(f" No uploads directory for {website_id}")
            return
        
        data_file = os.path.join(website_dir, "website_data.json")
        if not os.path.exists(data_file):
            print(f" No website data found for {website_id}")
            return
        
        with open(data_file, 'r', encoding='utf-8') as f:
            website_data = json.load(f)
        
        all_documents = website_data.copy()
        
        # Load processed uploads
        processed_files = []
        for filename in os.listdir(upload_dir):
            if filename.endswith('_processed.json'):
                processed_files.append(os.path.join(upload_dir, filename))
        
        print(f" Found {len(processed_files)} processed files to include")
        
        for processed_file in processed_files:
            try:
                with open(processed_file, 'r', encoding='utf-8') as f:
                    uploaded_docs = json.load(f)
                    all_documents.extend(uploaded_docs)
                    print(f" Added {len(uploaded_docs)} chunks from {processed_file}")
            except Exception as e:
                print(f" Error loading processed file {processed_file}: {e}")
        
        print(f"   Reindexing with {len(all_documents)} total documents "
              f"({len(website_data)} website + {len(all_documents) - len(website_data)} uploaded)")
        
        # Only reindex if there are new documents
        if len(all_documents) > len(website_data):
            embedding_handler = EmbeddingHandler()
            embedding_info = embedding_handler.create_embeddings(website_id, all_documents)
            
            print(f" Reindex completed: {len(all_documents)} documents indexed")
            
            # Update training info
            info_file = os.path.join(website_dir, "training_info.json")
            if os.path.exists(info_file):
                with open(info_file, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                
                info["total_documents"] = len(all_documents)
                info["uploaded_documents"] = len(all_documents) - len(website_data)
                info["last_reindex"] = datetime.now().isoformat()
                
                with open(info_file, 'w', encoding='utf-8') as f:
                    json.dump(info, f, ensure_ascii=False, indent=2)
            
            db_manager.save_training_log(website_id, {
                'status': 'completed',
                'message': f'Reindexing completed with {len(all_documents)} documents',
                'data_points': len(all_documents),
                'embedding_count': len(all_documents)
            })
            
            print(f"✅ Reindex completed successfully!")
        else:
            print(f" No new documents to index")
        
        return True
        
    except Exception as e:
        print(f"  Reindex error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


@router.get("/{website_id}")
async def get_website_uploads(website_id: str):
    """Get all uploads for a website"""
    try:
        website_dir = os.path.join("data", website_id)
        upload_dir = os.path.join(website_dir, "uploads")
        
        if not os.path.exists(upload_dir):
            return {
                "success": True,
                "website_id": website_id,
                "uploads": [],
                "files": [],
                "upload_count": 0
            }
        
        uploads_meta = os.path.join(upload_dir, "uploads_metadata.json")
        uploads = []
        if os.path.exists(uploads_meta):
            with open(uploads_meta, 'r') as f:
                uploads = json.load(f)
        
        files = []
        for filename in os.listdir(upload_dir):
            if not filename.endswith(('_processed.json', '_metadata.json')):
                file_path = os.path.join(upload_dir, filename)
                if os.path.isfile(file_path):
                    stat = os.stat(file_path)
                    files.append({
                        "filename": filename,
                        "path": file_path,
                        "size": stat.st_size,
                        "type": filename.split('.')[-1].upper() if '.' in filename else "UNKNOWN",
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
        
        # Sort files by modified date (newest first)
        files.sort(key=lambda x: x['modified'], reverse=True)
        
        return {
            "success": True,
            "website_id": website_id,
            "uploads": uploads,
            "files": files,
            "upload_count": len(uploads)
        }
        
    except Exception as e:
        print(f"  Get uploads error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Failed to get uploads",
                "message": str(e)
            }
        )


@router.delete("/{website_id}")
async def delete_uploaded_file(
    website_id: str, 
    request: Dict[str, Any], 
    user: dict = Depends(get_current_user)
):
    """Delete uploaded file from both filesystem and database"""
    try:
        filename = request.get('filename')
        if not filename:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "Filename required",
                    "message": "Please provide filename to delete"
                }
            )
        
        website = db_manager.get_website(website_id)
        if not website:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Website not found",
                    "message": f"Website with ID {website_id} not found."
                }
            )
        
        if website.get('user_id') != user['id'] and user.get('role') != 'admin':
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "error": "Permission denied",
                    "message": "You don't have permission to delete files from this website."
                }
            )
        
        website_dir = os.path.join("data", website_id)
        upload_dir = os.path.join(website_dir, "uploads")
        
        if not os.path.exists(upload_dir):
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Upload directory not found",
                    "message": f"Upload directory not found for website {website_id}"
                }
            )
        
        # Delete main file
        file_path = os.path.join(upload_dir, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f" Deleted file: {file_path}")
        
        # Delete processed file
        processed_file = os.path.join(upload_dir, f"{filename}_processed.json")
        if os.path.exists(processed_file):
            os.remove(processed_file)
            print(f" Deleted processed file: {processed_file}")
        
        # Delete from database
        try:
            conn = db_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM website_files WHERE website_id = %s AND filename = %s",
                (website_id, filename)
            )
            conn.commit()
            cursor.close()
        except Exception as db_error:
            print(f" Error deleting from database: {db_error}")
        
        # Update metadata
        uploads_meta = os.path.join(upload_dir, "uploads_metadata.json")
        if os.path.exists(uploads_meta):
            try:
                with open(uploads_meta, 'r') as f:
                    uploads_data = json.load(f)
                
                uploads_data = [u for u in uploads_data if u.get('saved_filename') != filename]
                
                with open(uploads_meta, 'w') as f:
                    json.dump(uploads_data, f, indent=2)
                
                print(f"Updated uploads metadata for {website_id}")
                
            except Exception as meta_error:
                print(f" Error updating metadata: {meta_error}")
        
        return {
            "success": True,
            "message": f"File {filename} deleted successfully",
            "website_id": website_id,
            "filename": filename
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"  Delete file error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Deletion failed",
                "message": str(e)
            }
        )