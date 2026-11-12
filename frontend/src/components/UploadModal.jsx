import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { UploadCloud, X, File, FileText, FileImage, CheckCircle, AlertCircle, Loader, Circle, Check } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const STAGES = [
  { id: 'uploading', label: 'Upload Started', duration: '0.2s' },
  { id: 'ocr', label: 'OCR Extraction Completed', duration: '1.2s' },
  { id: 'metadata', label: 'Metadata Validation Completed', duration: '0.8s' },
  { id: 'fraud', label: 'Fraud Analysis Running', duration: '1.5s' },
  { id: 'scoring', label: 'Risk Score Generated', duration: '0.4s' },
  { id: 'report', label: 'Report Finalized', duration: '0.1s' }
];

const UploadModal = ({ isOpen, onClose, onUploadComplete }) => {
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState('idle'); // idle, processing, success, error
  const [currentStageIndex, setCurrentStageIndex] = useState(-1);
  const [errorMessage, setErrorMessage] = useState('');
  const inputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  const handleFile = (selectedFile) => {
    const validTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff', 'image/bmp'];
    if (!validTypes.includes(selectedFile.type) && !selectedFile.name.match(/\.(pdf|jpg|jpeg|png|tiff|bmp)$/i)) {
      setErrorMessage('Unsupported file type. Please upload PDF, JPG, or PNG.');
      setUploadStatus('error');
      setFile(selectedFile);
      return;
    }
    
    if (selectedFile.size > 50 * 1024 * 1024) {
      setErrorMessage('File exceeds 50MB limit.');
      setUploadStatus('error');
      setFile(selectedFile);
      return;
    }

    setFile(selectedFile);
    setUploadStatus('idle');
    setErrorMessage('');
    setCurrentStageIndex(-1);
  };

  const onButtonClick = () => {
    inputRef.current.click();
  };

  const formatBytes = (bytes, decimals = 2) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  };

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  const handleUpload = async () => {
    if (!file) return;

    setUploadStatus('processing');
    setCurrentStageIndex(0); // Uploading

    const formData = new FormData();
    formData.append('file', file);

    try {
      const uploadRes = await axios.post('http://localhost:8000/api/v1/documents/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      const docId = uploadRes.data.document_id;
      const isDuplicate = uploadRes.data.status === 'duplicate';
      
      setCurrentStageIndex(1); // OCR
      await sleep(1000); // Simulate processing time for demo realism
      
      setCurrentStageIndex(2); // Metadata
      await sleep(800);
      
      setCurrentStageIndex(3); // Fraud Detection
      
      let fullRes;
      if (isDuplicate) {
        // Skip re-analysis, fetch the existing result directly
        fullRes = await axios.get(`http://localhost:8000/api/v1/analysis/document/${docId}`);
      } else {
        const analyzeRes = await axios.post(`http://localhost:8000/api/v1/analysis/${docId}/analyze`);
        fullRes = await axios.get(`http://localhost:8000/api/v1/analysis/${analyzeRes.data.analysis_id}`);
      }
      
      setCurrentStageIndex(4); // Scoring
      await sleep(600);
      
      setCurrentStageIndex(5); // Report
      const docRes = await axios.get(`http://localhost:8000/api/v1/documents/${docId}`);
      await sleep(500);

      setCurrentStageIndex(6); // Completed
      setUploadStatus('success');
      
      setTimeout(() => {
        onUploadComplete({
          analysis: fullRes.data,
          document: docRes.data
        });
        resetState();
        onClose();
      }, 1000);

    } catch (error) {
      console.error('Upload/Analysis error:', error);
      setUploadStatus('error');
      if (error.response?.data?.detail) {
        setErrorMessage(error.response.data.detail);
      } else {
        setErrorMessage('An error occurred during upload or analysis.');
      }
    }
  };

  const resetState = () => {
    setFile(null);
    setUploadStatus('idle');
    setCurrentStageIndex(-1);
    setErrorMessage('');
  };

  const handleClose = () => {
    if (uploadStatus === 'processing') return; 
    resetState();
    onClose();
  };

  const getFileIcon = () => {
    if (!file) return <File size={20} />;
    if (file.type === 'application/pdf') return <FileText size={20} className="text-blue-400" />;
    if (file.type.startsWith('image/')) return <FileImage size={20} className="text-emerald-400" />;
    return <File size={20} />;
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className={`modal-overlay ${isOpen ? 'open' : ''}`} onClick={handleClose}>
        <motion.div 
          className="modal-content"
          initial={{ opacity: 0, y: 20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 20, scale: 0.95 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="modal-header">
            <h2 className="modal-title">Intelligent Document Scanning</h2>
            <button className="close-btn" onClick={handleClose} disabled={uploadStatus === 'processing'}>
              <X size={20} />
            </button>
          </div>

          {!file ? (
            <div 
              className={`drop-zone ${dragActive ? 'dragover' : ''}`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={onButtonClick}
            >
              <input 
                ref={inputRef}
                type="file" 
                className="file-input" 
                onChange={handleChange}
                onClick={(e) => e.stopPropagation()}
                accept=".pdf,.jpg,.jpeg,.png,.tiff,.bmp"
              />
              <div className="drop-icon">
                <UploadCloud size={24} />
              </div>
              <div className="drop-text">Drag & drop a document here</div>
              <div className="drop-subtext">Supports PDF, JPG, PNG up to 50MB</div>
            </div>
          ) : (
            <div className="upload-progress-container">
              <div className="upload-file-info mb-4" style={{ background: '#18181b', padding: '16px', borderRadius: '8px', border: '1px solid #27272a' }}>
                <div className="file-icon">
                  {getFileIcon()}
                </div>
                <div className="file-details" style={{ flex: 1 }}>
                  <div className="file-name" title={file.name}>{file.name}</div>
                  <div className="file-size">{formatBytes(file.size)}</div>
                </div>
                {uploadStatus === 'idle' && (
                  <button className="close-btn" onClick={() => setFile(null)}>
                    <X size={16} />
                  </button>
                )}
              </div>

              {(uploadStatus === 'processing' || uploadStatus === 'success') && (
                <div style={{ marginTop: '24px' }}>
                  <div style={{ fontSize: '14px', fontWeight: 600, color: '#fff', marginBottom: '16px' }}>Analysis Pipeline</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {STAGES.map((stage, idx) => {
                      const isCompleted = currentStageIndex > idx;
                      const isCurrent = currentStageIndex === idx;
                      const isPending = currentStageIndex < idx;

                      let icon;
                      let color = '#a1a1aa';
                      if (isCompleted || (idx === STAGES.length - 1 && uploadStatus === 'success')) {
                        icon = <CheckCircle size={16} />;
                        color = '#10b981';
                      } else if (isCurrent) {
                        icon = <Loader size={16} className="animate-spin" />;
                        color = '#3b82f6';
                      } else {
                        icon = <Circle size={16} />;
                        color = '#52525b';
                      }

                      return (
                        <div key={stage.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            {icon}
                            <span style={{ fontSize: '14px', fontWeight: isCurrent ? 500 : 400 }}>{stage.label}</span>
                          </div>
                          {isCompleted && <span style={{ fontSize: '12px', opacity: 0.7 }}>{stage.duration}</span>}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {uploadStatus === 'error' && (
                <div className="mt-4 text-sm" style={{ color: '#f43f5e', background: 'rgba(244,63,94,0.1)', padding: '12px', borderRadius: '6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <AlertCircle size={16} />
                  {errorMessage}
                </div>
              )}
            </div>
          )}

          <div className="mt-8 flex justify-end gap-3">
            <button 
              className="btn btn-ghost" 
              onClick={handleClose}
              disabled={uploadStatus === 'processing'}
            >
              Cancel
            </button>
            <button 
              className="btn btn-primary flex items-center gap-2" 
              onClick={handleUpload}
              disabled={!file || uploadStatus === 'processing' || uploadStatus === 'success'}
            >
              {uploadStatus === 'processing' && <Loader size={14} className="animate-spin" />}
              {uploadStatus === 'processing' ? 'Processing...' : 'Run Analysis'}
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};

export default UploadModal;
