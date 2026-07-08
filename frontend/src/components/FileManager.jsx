import React, { useRef, useState } from 'react';
import { FaUpload, FaSpinner, FaSync } from 'react-icons/fa';
import { toast } from 'react-hot-toast';
import api from './server/api';

// Import the api object

const API_URL = import.meta.env.VITE_API_BASE_URL;

const FileManager = ({ website, onUploadComplete }) => {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadPhase, setUploadPhase] = useState('');
  const [uploadStatus, setUploadStatus] = useState('');
  const [processingFiles, setProcessingFiles] = useState([]);
  const fileInputRef = useRef(null);

  const handleFileUpload = async (event) => {
    const selectedFiles = Array.from(event.target.files);
    if (selectedFiles.length === 0) return;

    setProcessingFiles(selectedFiles.map(f => f.name));
    setIsUploading(true);
    setUploadProgress(0);
    setUploadPhase('uploading');
    setUploadStatus('Starting upload...');

    try {
      // Use the api.uploadFiles method
      const result = await api.uploadFiles(
        website.website_id,
        selectedFiles,
        (e) => {
          if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            setUploadProgress(Math.min(percent, 30));
            setUploadStatus(`Uploading: ${percent}%`);
          }
        }
      );
      
      if (result.success) {
        setUploadProgress(100);
        setUploadPhase('complete');
        setUploadStatus('Complete!');
        toast.success(`Uploaded ${result.successful_uploads} file(s) successfully!`);
        if (onUploadComplete) onUploadComplete();
      } else {
        toast.error(result.message || 'Upload failed');
      }
      
    } catch (error) {
      console.error('Upload error:', error);
      toast.error(error.message || 'Upload failed');
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
      setUploadPhase('');
      setUploadStatus('');
      setProcessingFiles([]);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const getPhaseColor = () => {
    switch (uploadPhase) {
      case 'uploading': return 'bg-blue-500';
      case 'processing': return 'bg-yellow-500';
      case 'embedding': return 'bg-purple-500';
      case 'complete': return 'bg-green-500';
      default: return 'bg-blue-500';
    }
  };

  return (
    <>
      {/* Upload Overlay */}
      {isUploading && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full mx-4">
            <div className="text-center mb-6">
              <div className="w-20 h-20 mx-auto mb-4 relative">
                <div className="absolute inset-0 border-4 border-gray-200 rounded-full"></div>
                <div 
                  className={`absolute inset-0 border-4 ${getPhaseColor()} rounded-full transition-all duration-300`}
                  style={{ 
                    clipPath: `inset(0 ${100 - uploadProgress}% 0 0)`,
                    transform: 'rotate(90deg) scaleX(-1)'
                  }}
                ></div>
              </div>
              
              {/* Progress Bar */}
              <div className="w-full bg-gray-200 rounded-full h-3 mb-4">
                <div 
                  className={`${getPhaseColor()} h-3 rounded-full transition-all duration-300 relative`}
                  style={{ width: `${uploadProgress}%` }}
                >
                  <span className="absolute -right-8 -top-6 text-sm font-medium text-gray-700">
                    {uploadProgress}%
                  </span>
                </div>
              </div>
              
              {/* Upload Status */}
              <p className="text-sm font-medium text-gray-700 mb-2">{uploadStatus}</p>
              
              {/* Files being processed */}
              {processingFiles.length > 0 && (
                <div className="mt-4 text-left">
                  <p className="text-sm font-medium text-gray-700 mb-2">Uploading:</p>
                  <div className="max-h-32 overflow-y-auto space-y-1">
                    {processingFiles.map((fileName, index) => (
                      <div key={index} className="flex items-center space-x-2 text-sm">
                        <FaSpinner className="animate-spin text-blue-500 text-xs" />
                        <span className="text-gray-600 truncate">{fileName}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              <p className="text-xs text-gray-500 mt-4">
                Please don't close this window or navigate away
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Main Upload Section */}
      <div className={`space-y-6 ${isUploading ? 'pointer-events-none opacity-50' : ''}`}>
        {/* Website Info */}
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-5 border border-blue-200">
          <div>
            <h3 className="font-semibold text-gray-900 text-lg">{website.website_name}</h3>
            <p className="text-sm text-gray-600">ID: {website.website_id.substring(0, 12)}...</p>
          </div>
        </div>

        {/* Upload Section */}
        <div className="bg-white border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-blue-400 transition-colors">
          <label className="cursor-pointer">
            <div className="flex flex-col items-center justify-center space-y-4">
              <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center">
                <FaUpload className="text-blue-600 text-2xl" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">Upload Files</h3>
                <p className="text-gray-600 mb-4">
                  Upload PDF, Word, Excel, or text files to train your chatbot
                </p>
              </div>
              <div className="relative">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  onChange={handleFileUpload}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  disabled={isUploading}
                  accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.jpg,.jpeg,.png"
                />
                <div className={`px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors ${isUploading ? 'opacity-50 cursor-not-allowed' : ''}`}>
                  {isUploading ? 'Uploading...' : 'Choose Files'}
                </div>
              </div>
              <p className="text-xs text-gray-500">
                Max file size: 50MB. Supported: PDF, DOC, XLS, TXT, Images
              </p>
            </div>
          </label>
        </div>

        {/* Note */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-center">
          <p className="text-sm text-blue-700">
            After uploading, your files will appear in the "Uploaded Files" section below.
            You can preview, download, or delete files from there.
          </p>
        </div>
      </div>
    </>
  );
};

export default FileManager;