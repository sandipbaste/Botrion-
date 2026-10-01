// TrainingInterface.jsx
import React, { useState, useEffect, useRef } from 'react';
import { 
  FaSpinner, FaCheckCircle, FaGlobe, FaDatabase, FaRobot, 
  FaClock, FaArrowRight, FaCode, FaSave, FaCog, FaSearch,
  FaFileAlt, FaBrain, FaRocket, FaHourglassHalf
} from 'react-icons/fa';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'react-hot-toast';

const API_URL = import.meta.env.VITE_API_BASE_URL;

// Long-polling settings.
// Each request to /api/training/wait/<id> is held open by the server (up to
// WAIT_TIMEOUT_S seconds) and returns as soon as training completes or fails.
// So a 2-3 minute training makes only ~5-7 requests instead of dozens.
const WAIT_TIMEOUT_S = 20;
const MAX_WAIT_MS = 20 * 60 * 1000;  // 20 minutes
const MAX_FAILURES = 15;              // tolerate temporary failures
const MIN_GAP_MS = 3000;


const TrainingInterface = ({ onWebsiteTrained, onTrainingStart, onTrainingComplete, isProcessing }) => {
  const [websiteUrl, setWebsiteUrl] = useState('');
  const [websiteName, setWebsiteName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [trainingProgress, setTrainingProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(0);
  const [currentStage, setCurrentStage] = useState('');
  const [stageDetails, setStageDetails] = useState('');
  const [trainingComplete, setTrainingComplete] = useState(false);
  const [pagesExtracted, setPagesExtracted] = useState(0);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [websiteId, setWebsiteId] = useState(null);
  
  const progressInterval = useRef(null);
  const startTimeRef = useRef(null);
  const currentProgressRef = useRef(0);
  const waitSessionRef = useRef(0);    // bumping this cancels any running wait loop
  const waitAbortRef = useRef(null);   // aborts the in-flight request

  // Stop the wait loop (safe to call multiple times)
  const stopWaiting = () => {
    waitSessionRef.current += 1;
    if (waitAbortRef.current) {
      waitAbortRef.current.abort();
      waitAbortRef.current = null;
    }
  };

  // Continuous smooth progress function
  const continuousProgress = () => {
    if (currentProgressRef.current < 99) {
      const elapsedSeconds = (Date.now() - startTimeRef.current) / 1000;
      
      let increment = 0.1;
      
      if (elapsedSeconds < 10) {
        increment = 0.15;
      } else if (elapsedSeconds < 30) {
        increment = 0.1;
      } else if (elapsedSeconds < 60) {
        increment = 0.08;
      } else {
        increment = 0.05;
      }
      
      increment += (Math.random() * 0.04) - 0.02;
      
      const newProgress = Math.min(currentProgressRef.current + increment, 99);
      currentProgressRef.current = newProgress;
      setTrainingProgress(newProgress);
      updateStageFromProgress(newProgress);
    }
  };

  // Update stage based on continuous progress
  const updateStageFromProgress = (progress) => {
    if (progress < 10) {
      setCurrentStage('Initializing');
      setStageDetails('Preparing training environment...');
      setCurrentStep(1);
    } else if (progress < 20) {
      setCurrentStage('Connecting to Website');
      setStageDetails('Establishing connection to target website...');
      setCurrentStep(2);
    } else if (progress < 30) {
      setCurrentStage('Discovering Pages');
      setStageDetails(`Scanning website structure... Found ${pagesExtracted} pages so far`);
      setCurrentStep(3);
    } else if (progress < 40) {
      setCurrentStage('Crawling Content');
      setStageDetails('Extracting content from website pages...');
      setCurrentStep(4);
    } else if (progress < 50) {
      setCurrentStage('Processing Pages');
      setStageDetails(`Processing ${pagesExtracted} pages for embedding...`);
      setCurrentStep(5);
    } else if (progress < 60) {
      setCurrentStage('Cleaning Content');
      setStageDetails('Cleaning and organizing extracted content...');
      setCurrentStep(6);
    } else if (progress < 70) {
      setCurrentStage('Loading AI Model');
      setStageDetails('Loading OpenAI embedding model...');
      setCurrentStep(7);
    } else if (progress < 80) {
      setCurrentStage('Creating Embeddings');
      setStageDetails('Converting text to AI embeddings...');
      setCurrentStep(8);
    } else if (progress < 90) {
      setCurrentStage('Storing in Qdrant');
      setStageDetails('Saving embeddings to Qdrant Cloud...');
      setCurrentStep(9);
    } else if (progress < 95) {
      setCurrentStage('Generating Script');
      setStageDetails('Creating chatbot JavaScript file...');
      setCurrentStep(10);
    } else if (progress < 99) {
      setCurrentStage('Finalizing');
      setStageDetails('Completing training process...');
      setCurrentStep(11);
    } else {
      setCurrentStage('Almost Done');
      setStageDetails('Finalizing...');
      setCurrentStep(12);
    }
  };

  // Start continuous progress animation
  useEffect(() => {
    if (isProcessing && !trainingComplete) {
      progressInterval.current = setInterval(continuousProgress, 200);
      
      startTimeRef.current = Date.now();
      const timeInterval = setInterval(() => {
        if (startTimeRef.current) {
          const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000);
          setElapsedTime(elapsed);
        }
      }, 1000);
      
      return () => {
        clearInterval(progressInterval.current);
        clearInterval(timeInterval);
      };
    }
  }, [isProcessing, trainingComplete]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!websiteUrl) {
      toast.error('Please enter a website URL');
      return;
    }
    
    if (!contactEmail) {
      toast.error('Please enter a contact email');
      return;
    }
    
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(contactEmail)) {
      toast.error('Please enter a valid email address');
      return;
    }
    
    // Make sure no old wait loop is still running
    stopWaiting();
    
    onTrainingStart();
    
    // Reset all progress values
    setTrainingProgress(0);
    setCurrentStage('Initializing');
    setStageDetails('Starting training process...');
    setPagesExtracted(0);
    setElapsedTime(0);
    setTrainingComplete(false);
    setCurrentStep(1);
    setWebsiteId(null);
    
    currentProgressRef.current = 0;
    startTimeRef.current = Date.now();
    
    try {
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(`${API_URL}/api/train`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          website_url: websiteUrl,
          website_name: websiteName || undefined,
          contact_email: contactEmail,
          generate_script: true
        })
      });
      
      const data = await response.json();
      
      if (!data.success) {
        throw new Error(data.message || 'Training failed');
      }
      
      const newWebsiteId = data.website_id;
      setWebsiteId(newWebsiteId);
      
      // ---------- Wait for training to finish (long-polling) ----------
      const session = waitSessionRef.current;   // this loop is valid only while this matches
      const startedAt = Date.now();
      let failures = 0;

      const giveUp = (message) => {
        stopWaiting();
        setCurrentStage('Error');
        setStageDetails(message);
        toast.error(message);
        onTrainingComplete();
      };

      const waitForTraining = async () => {
        while (session === waitSessionRef.current) {
          if (Date.now() - startedAt > MAX_WAIT_MS) {
            giveUp('Training is taking too long. Please check My Websites later.');
            return;
          }

          const requestStarted = Date.now();
          const controller = new AbortController();
          waitAbortRef.current = controller;

          try {
            const statusResponse = await fetch(
              `${API_URL}/api/training/wait/${newWebsiteId}?timeout=${WAIT_TIMEOUT_S}`,
              {
                  headers: {
                      Authorization: `Bearer ${token}`,
                      'Content-Type': 'application/json'
                  },
                  signal: controller.signal
              }
          );

          // Handle temporary Render/server errors
          if (
              statusResponse.status === 502 ||
              statusResponse.status === 503 ||
              statusResponse.status === 504
          ) {
              console.warn(
                  `Temporary server error: ${statusResponse.status}`
              );

              failures += 1;

              if (failures >= MAX_FAILURES) {
                  giveUp(
                      'The training server is temporarily unavailable. ' +
                      'Please try again later.'
                  );
                  return;
              }

              await new Promise(resolve =>
                  setTimeout(resolve, 5000)
              );

              continue;
          }

          // Handle expired login
          if (statusResponse.status === 401) {
              giveUp('Your session has expired. Please login again.');
              return;
          }

          // Handle other HTTP errors
          if (!statusResponse.ok) {
              throw new Error(
                  `Training status request failed: ${statusResponse.status}`
              );
          }

          const statusData = await statusResponse.json();

            // Cancelled while the request was in flight
            if (session !== waitSessionRef.current) return;

            if (statusData.success) {
              failures = 0;

              if (statusData.data_points !== undefined) {
                setPagesExtracted(statusData.data_points);
              }

              if (statusData.progress !== undefined && statusData.progress > 0) {
                currentProgressRef.current = Math.max(
                  currentProgressRef.current,
                  statusData.progress
                );
                setTrainingProgress(currentProgressRef.current);
              }

              // =========================
              // TRAINING COMPLETED
              // =========================
              if (statusData.status === 'completed') {
                stopWaiting();

                currentProgressRef.current = 100;
                setTrainingProgress(100);

                setCurrentStage('Completed');
                setStageDetails('Training completed successfully!');
                setCurrentStep(12);
                setTrainingComplete(true);

                setTimeout(() => {
                  const websiteObj = {
                    website_id: newWebsiteId,
                    website_name:
                      statusData.website_name ||
                      websiteName ||
                      websiteUrl,
                    website_url: websiteUrl,
                    admin_email: contactEmail,
                    status: 'active',
                    created_at: new Date().toISOString(),
                    data_points: statusData.data_points || pagesExtracted || 0,
                    upload_count: 0
                  };

                  onWebsiteTrained(websiteObj);
                  toast.success('🤖 Chatbot trained successfully!');
                  onTrainingComplete();
                }, 500);

                return;
              }

              // =========================
              // TRAINING ERROR
              // =========================
              if (statusData.status === 'error') {
                stopWaiting();

                setCurrentStage('Error');
                setStageDetails(statusData.message || 'Training failed');
                toast.error(statusData.message || 'Training failed');
                onTrainingComplete();

                return;
              }
            } else {
              // success:false (e.g. "Training not found" after a server restart)
              failures += 1;
              if (failures >= MAX_FAILURES) {
                giveUp(statusData.message || 'Training status not found');
                return;
              }
            }
          } catch (error) {
            // Aborted on purpose (unmount / new training) - just stop
            if (error.name === 'AbortError') return;
            if (session !== waitSessionRef.current) return;

            console.error('Error waiting for training:', error);

            failures += 1;
            if (failures >= MAX_FAILURES) {
                giveUp(
                    'Unable to check training status right now. ' +
                    'Your training may still be running. Please check My Websites later.'
                );
                return;
            }
          }

          // Safety: if the server answered instantly, don't loop faster than MIN_GAP_MS
          const elapsed = Date.now() - requestStarted;
          if (elapsed < MIN_GAP_MS) {
            await new Promise((resolve) => setTimeout(resolve, MIN_GAP_MS - elapsed));
          }
        }
      };

    await waitForTraining();
  }    
  catch (error) {
    if (error.name === 'AbortError') return;
    if (session !== waitSessionRef.current) return;

    console.error('Error waiting for training:', error);

    failures += 1;

    // Keep showing training progress during temporary network/server errors
    if (failures < MAX_FAILURES) {
        setStageDetails(
            `Training is still running... reconnecting (${failures}/${MAX_FAILURES})`
        );
    }

    if (failures >= MAX_FAILURES) {
        giveUp(
            'Unable to connect to the training service. ' +
            'The training may still be running. Please check My Websites later.'
        );
        return;
    }
  }
  

  // Stop waiting when the component unmounts
  useEffect(() => {
    return () => {
      stopWaiting();
    };
  }, []);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Train New Chatbot</h2>
      
      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Website URL *
          </label>
          <input
            type="url"
            value={websiteUrl}
            onChange={(e) => setWebsiteUrl(e.target.value)}
            placeholder="https://example.com"
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            disabled={isProcessing}
            required
          />
          <p className="mt-1 text-sm text-gray-500">
            Enter the full URL of the website you want to train the chatbot on
          </p>
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Chatbot Name (Optional)
          </label>
          <input
            type="text"
            value={websiteName}
            onChange={(e) => setWebsiteName(e.target.value)}
            placeholder="My Awesome Website"
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            disabled={isProcessing}
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Contact Email *
          </label>
          <input
            type="email"
            value={contactEmail}
            onChange={(e) => setContactEmail(e.target.value)}
            placeholder="admin@example.com"
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            disabled={isProcessing}
            required
          />
          <p className="mt-1 text-sm text-gray-500">
            Email where you'll receive notifications and chat reports
          </p>
        </div>
        
        <button
          type="submit"
          disabled={isProcessing}
          className="w-full cursor-pointer px-6 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-medium rounded-xl hover:from-blue-700 hover:to-indigo-700 transition-all duration-200 disabled:opacity-70 disabled:cursor-not-allowed"
        >
          {isProcessing ? 'Training in Progress...' : 'Start Training'}
        </button>
      </form>
      
      {/* Progress Popup Modal */}
      <AnimatePresence>
        {isProcessing && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="fixed inset-0 flex items-center justify-center z-50 p-4"
            style={{ backgroundColor: 'rgba(0, 0, 0, 0.5)' }}
          >
            <motion.div
              initial={{ y: 50 }}
              animate={{ y: 0 }}
              className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
            >
              <div className="p-6">
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center space-x-3">
                    <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center">
                      <FaRobot className="text-blue-600 text-xl" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">Training Progress</h3>
                      <p className="text-sm text-gray-500">Website: {websiteName || websiteUrl}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-blue-600">
                      {trainingComplete ? '100%' : `${Math.min(99, Math.round(trainingProgress))}%`}
                    </div>
                    <div className="text-xs text-gray-400 flex items-center">
                      <FaClock className="mr-1" /> {formatTime(elapsedTime)}
                    </div>
                  </div>
                </div>
                
                {/* Main Progress Bar */}
                <div className="mb-8">
                  <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
                    <motion.div
                      className="h-full bg-gradient-to-r from-blue-500 to-indigo-600"
                      initial={{ width: 0 }}
                      animate={{ width: `${trainingComplete ? 100 : trainingProgress}%` }}
                      transition={{ duration: 0.2 }}
                    />
                  </div>
                </div>
                
                {/* Current Step with Live Updates */}
                <div className="mb-4 text-center">
                  <div className={`inline-block rounded-full px-4 py-2 ${
                    trainingComplete ? 'bg-green-100' : 'bg-blue-100'
                  }`}>
                    <span className={`text-sm font-medium ${
                      trainingComplete ? 'text-green-700' : 'text-blue-700'
                    }`}>
                      {trainingComplete ? '✅ Training Complete!' : `Step ${currentStep} of 12 • ${currentStage}`}
                    </span>
                  </div>
                </div>
                
                {/* Live Stats Grid */}
                <div className="mb-6">
                  <div className="bg-green-50 p-3 rounded-lg text-center">
                    <div className="text-xs text-gray-600">Est. Remaining</div>
                    <div className="text-xl font-bold text-green-700">
                      {trainingComplete ? 'Done!' :
                       trainingProgress < 20 ? '3-4 min' :
                       trainingProgress < 40 ? '2-3 min' :
                       trainingProgress < 60 ? '1-2 min' :
                       trainingProgress < 80 ? '45-60 sec' :
                       trainingProgress < 95 ? '30 sec' :
                       'Few seconds'}
                    </div>
                  </div>
                </div>
                
                {/* Current Action with Continuous Progress */}
                <div className={`p-4 rounded-lg border ${
                  trainingComplete ? 'bg-green-50 border-green-200' : 'bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200'
                } mb-4`}>
                  <div className="flex items-center">
                    <div className="mr-3 text-2xl">
                      {trainingComplete ? 
                        <FaCheckCircle className="text-green-500" /> : 
                        <FaHourglassHalf className="text-blue-500 animate-pulse" />
                      }
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-gray-900">
                        {trainingComplete ? 'Complete!' : currentStage}
                      </p>
                      <p className="text-xs text-gray-600">{stageDetails}</p>
                      
                      {/* Micro progress bar for current action */}
                      {!trainingComplete && (
                        <div className="mt-2 w-full bg-blue-200 rounded-full h-1.5">
                          <motion.div
                            className="h-full bg-blue-600 rounded-full"
                            initial={{ width: 0 }}
                            animate={{ width: `${(trainingProgress % 10) * 10}%` }}
                            transition={{ duration: 0.3 }}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                
                {/* Progress Message */}
                <div className="text-center">
                  <p className="text-xs text-gray-400">
                    {trainingComplete ? 
                      'Your chatbot is ready to use!' : 
                      'Progress continues during extraction • Training in progress...'}
                  </p>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
}
export default TrainingInterface;