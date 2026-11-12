import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';
import { 
  ArrowLeft, Printer, ShieldAlert, CheckCircle, AlertTriangle, 
  Check, Search, ChevronDown, ChevronUp, FileText, Database, 
  Shield, Clock, Send, MessageSquare, AlertCircle, FileCheck
} from 'lucide-react';
import DocumentViewer from './DocumentViewer';

const DocumentInsights = ({ analysisId, documentId, currentUser, onBack, onDecisionSuccess }) => {
  const [activeTab, setActiveTab] = useState('overview');
  const [activeDocIndex, setActiveDocIndex] = useState(0);
  const [ocrOpen, setOcrOpen] = useState(false);
  const [ocrViewMode, setOcrViewMode] = useState('structured');
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedIssueIndex, setSelectedIssueIndex] = useState(() => {
    const saved = localStorage.getItem('selectedIssueIndex');
    return saved !== null ? parseInt(saved, 10) : null;
  });

  useEffect(() => {
    if (selectedIssueIndex !== null) {
      localStorage.setItem('selectedIssueIndex', String(selectedIssueIndex));
    } else {
      localStorage.removeItem('selectedIssueIndex');
    }
  }, [selectedIssueIndex]);

  const [noteText, setNoteText] = useState('');
  const [decisionType, setDecisionType] = useState('approved'); // APPROVED, REJECTED, CLOSED
  const [decisionComment, setDecisionComment] = useState('');
  const [explicitConfirmation, setExplicitConfirmation] = useState(false);
  const [isSubmittingNote, setIsSubmittingNote] = useState(false);
  const [isSubmittingDecision, setIsSubmittingDecision] = useState(false);
  const [actionError, setActionError] = useState('');
  const [actionSuccess, setActionSuccess] = useState('');

  // 1. Fetch Case Details
  const { data: caseDetails, isLoading: isLoadingCase, refetch: refetchCase } = useQuery({
    queryKey: ['case', analysisId],
    queryFn: async () => {
      const res = await axios.get(`http://localhost:8000/api/v1/cases/${analysisId}`);
      return res.data;
    },
    enabled: !!analysisId,
  });

  const activeDocument = caseDetails?.documents?.[activeDocIndex];
  const activeDocumentId = activeDocument?.id;

  // 2. Fetch Active Document Analysis
  const { data: activeAnalysis, isLoading: isLoadingAnalysis, refetch: refetchAnalysis } = useQuery({
    queryKey: ['activeAnalysis', activeDocumentId],
    queryFn: async () => {
      if (!activeDocumentId) return null;
      const res = await axios.get(`http://localhost:8000/api/v1/analysis/document/${activeDocumentId}`);
      return res.data;
    },
    enabled: !!activeDocumentId,
  });

  // 3. Investigator Q&A Chat State
  const [chatQuestion, setChatQuestion] = useState('');
  const [chatHistory, setChatHistory] = useState([
    { role: 'assistant', text: 'Hi! I am the SecureDocXAI reasoning assistant. Ask me anything about these case documents.' }
  ]);
  const [isAsking, setIsAsking] = useState(false);

  const handleAskChat = async (e) => {
    e.preventDefault();
    if (!chatQuestion.trim()) return;
    const userText = chatQuestion;
    setChatQuestion('');
    setChatHistory(prev => [...prev, { role: 'user', text: userText }]);
    setIsAsking(true);
    try {
      const res = await axios.post(`http://localhost:8000/api/v1/cases/${analysisId}/qa`, {
        question: userText
      });
      setChatHistory(prev => [...prev, { role: 'assistant', text: res.data.answer }]);
    } catch (err) {
      console.error(err);
      setChatHistory(prev => [...prev, { role: 'assistant', text: 'Failed to retrieve answer from reasoning engine. Check server connection.' }]);
    } finally {
      setIsAsking(false);
    }
  };

  const handleAddNote = async (e) => {
    e.preventDefault();
    if (!noteText.trim()) return;
    setIsSubmittingNote(true);
    setActionError('');
    setActionSuccess('');
    try {
      await axios.post(`http://localhost:8000/api/v1/cases/${analysisId}/notes`, {
        text: noteText
      });
      setNoteText('');
      setActionSuccess('Note added successfully!');
      refetchCase();
    } catch (err) {
      console.error(err);
      setActionError(err.response?.data?.detail || 'Failed to add note');
    } finally {
      setIsSubmittingNote(false);
    }
  };

  const handleDecision = async (e) => {
    e.preventDefault();
    if (!decisionComment.trim()) {
      setActionError('Decision comment/justification is required');
      return;
    }
    
    // Safety check for CRITICAL approval
    const priority = caseDetails?.priority || 'LOW';
    const hasAnalystNotes = caseDetails?.notes?.some(n => n.role === 'Fraud Analyst' || n.role === 'analyst');
    if (decisionType === 'APPROVED' && priority === 'CRITICAL') {
      if (!explicitConfirmation) {
        setActionError('Explicit confirmation checkbox is required for CRITICAL case approval.');
        return;
      }
      if (decisionComment.trim().length < 10) {
        setActionError('A detailed override justification (at least 10 characters) is required for CRITICAL cases.');
        return;
      }
      if (!hasAnalystNotes) {
        setActionError('Cannot approve CRITICAL cases: No Fraud Analyst notes exist on this case.');
        return;
      }
    }

    setIsSubmittingDecision(true);
    setActionError('');
    setActionSuccess('');
    try {
      await axios.post(`http://localhost:8000/api/v1/cases/${analysisId}/decide`, {
        decision: decisionType,
        justification: decisionComment
      });
      setDecisionComment('');
      setExplicitConfirmation(false);
      setActionSuccess(`Case successfully resolved as ${decisionType.toUpperCase()}!`);
      refetchCase();
      if (onDecisionSuccess) onDecisionSuccess();
    } catch (err) {
      console.error(err);
      setActionError(err.response?.data?.detail || 'Failed to submit decision');
    } finally {
      setIsSubmittingDecision(false);
    }
  };

  const handleAssignToMe = async () => {
    setActionError('');
    setActionSuccess('');
    try {
      await axios.post(`http://localhost:8000/api/v1/cases/${analysisId}/assign`);
      setActionSuccess('Case successfully assigned to you!');
      refetchCase();
      if (onDecisionSuccess) onDecisionSuccess();
    } catch (err) {
      console.error(err);
      setActionError(err.response?.data?.detail || 'Failed to assign case');
    }
  };

  const handleEscalateCase = async (reason) => {
    if (!reason.trim()) {
      setActionError('Escalation reason is required.');
      return;
    }
    setActionError('');
    setActionSuccess('');
    try {
      await axios.post(`http://localhost:8000/api/v1/cases/${analysisId}/escalate`, {
        reason: reason
      });
      setActionSuccess('Case successfully escalated to manager!');
      refetchCase();
      if (onDecisionSuccess) onDecisionSuccess();
    } catch (err) {
      console.error(err);
      setActionError(err.response?.data?.detail || 'Failed to escalate case');
    }
  };

  const handlePrint = () => {
    window.open(`http://localhost:8000/api/v1/cases/${analysisId}/report`, '_blank');
  };

  if (isLoadingCase) {
    return (
      <div className="content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div style={{ color: '#a1a1aa' }}>Loading SecureDocXAI investigation workspace...</div>
      </div>
    );
  }

  if (!caseDetails) {
    return (
      <div className="content">
        <button className="btn btn-ghost" onClick={onBack}><ArrowLeft size={16}/> Back</button>
        <div style={{ marginTop: '20px', color: '#f43f5e' }}>Error loading case details.</div>
      </div>
    );
  }

  const compositeRiskScore = Math.round(caseDetails.risk_score?.composite || 0);
  const trustScore = Math.round(caseDetails.trust_score?.score || 100);
  const detectedIssues = caseDetails.risk_score?.detected_issues || [];
  const execSummary = caseDetails.explanation?.executive_summary || caseDetails.explanation?.summary;
  const statusBadge = caseDetails.status || 'UNASSIGNED';

  const getStatusDetails = (s) => {
    switch (s.toUpperCase()) {
      case 'APPROVED': return { color: '#10b981', icon: <CheckCircle size={28} /> };
      case 'CLOSED': return { color: '#34d399', icon: <Check size={28} /> };
      case 'UNDER_REVIEW': return { color: '#f59e0b', icon: <Search size={28} /> };
      case 'ESCALATED': return { color: '#f97316', icon: <AlertTriangle size={28} /> };
      case 'REJECTED': return { color: '#f43f5e', icon: <ShieldAlert size={28} /> };
      default: return { color: '#a1a1aa', icon: <Search size={28} /> };
    }
  };

  const statusInfo = getStatusDetails(statusBadge);
  const isHighRisk = statusBadge === 'REJECTED' || statusBadge === 'ESCALATED';
  const role = currentUser?.role;

  return (
    <div className="content document-insights" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 65px)', overflow: 'hidden' }}>
      {/* Header Area */}
      <div className="section-header print-hide" style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button className="icon-btn" onClick={onBack} title="Back to Queue">
            <ArrowLeft size={16} />
          </button>
          <div>
            <div className="section-title" style={{ fontSize: '18px', fontWeight: 600 }}>{caseDetails.case_name || 'Investigation Case'}</div>
            <div className="section-sub" style={{ fontSize: '12px' }}>
              Case Ref: <strong>{caseDetails.case_id}</strong> • Priority: <span style={{ color: caseDetails.priority === 'CRITICAL' ? '#f43f5e' : '#f97316', fontWeight: 700 }}>{caseDetails.priority}</span>
            </div>
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: '12px' }}>
          <button className="btn btn-ghost flex items-center gap-2" onClick={handlePrint} style={{ fontSize: '13px', padding: '6px 14px' }}>
            <Printer size={15} /> Export Audit Report
          </button>
          
          {(role === 'Branch Manager' || role === 'System Admin') && (
            <button 
              className="btn btn-primary"
              onClick={() => {
                const el = document.getElementById('decision-section-anchor');
                if (el) el.scrollIntoView({ behavior: 'smooth' });
              }}
              style={{ fontSize: '13px', padding: '6px 14px' }}
            >
              Resolve Action
            </button>
          )}
        </div>
      </div>

      {/* Main Split-Screen Workspace Grid */}
      <div className="insights-grid" style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '20px', flex: 1, overflow: 'hidden' }}>
        
        {/* Left Column: Visual tabbed Document Viewer */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', border: '1px solid #27272a' }}>
          {/* Document Tabs */}
          <div style={{ display: 'flex', gap: '4px', background: '#18181b', padding: '8px 12px 0 12px', borderBottom: '1px solid #27272a', overflowX: 'auto' }}>
            {caseDetails.documents?.map((doc, idx) => (
              <button
                key={doc.id}
                onClick={() => {
                  setActiveDocIndex(idx);
                  setCurrentPage(1);
                }}
                style={{
                  padding: '8px 14px',
                  borderRadius: '6px 6px 0 0',
                  border: '1px solid #27272a',
                  borderBottom: activeDocIndex === idx ? '1px solid #09090b' : '1px solid #27272a',
                  cursor: 'pointer',
                  fontSize: '12px',
                  fontWeight: 600,
                  transition: 'all 0.15s',
                  background: activeDocIndex === idx ? '#09090b' : 'rgba(255,255,255,0.01)',
                  color: activeDocIndex === idx ? '#3b82f6' : '#a1a1aa',
                  whiteSpace: 'nowrap'
                }}
              >
                📄 {doc.original_filename || doc.filename}
              </button>
            ))}
          </div>

          {activeDocument ? (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <DocumentViewer 
                  fileUrl={`http://localhost:8000/uploads/${activeDocument.filename}`}
                  fileType={activeDocument.file_type}
                  fileName={activeDocument.original_filename || activeDocument.filename}
                  documentId={activeDocument.id}
                  pageCount={activeDocument.page_count || 1}
                  currentPage={currentPage}
                  onPageChange={setCurrentPage}
                  detectedIssues={role !== 'Compliance Auditor' ? (activeAnalysis?.results?.risk_score?.detected_issues || []) : []}
                  selectedIssueIndex={selectedIssueIndex}
              />
            </div>
          ) : (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#71717a' }}>
              No documents associated with this case.
            </div>
          )}
        </div>

        {/* Right Column: Case Management & Insights */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto', paddingRight: '4px' }}>
          
          {/* Action alerts */}
          {actionSuccess && (
            <div style={{ background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.2)', padding: '12px', borderRadius: '8px', color: '#10b981', fontSize: '13px', display: 'flex', gap: '8px', alignItems: 'center' }}>
              <CheckCircle size={16} /> {actionSuccess}
            </div>
          )}
          {actionError && (
            <div style={{ background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.2)', padding: '12px', borderRadius: '8px', color: '#f43f5e', fontSize: '13px', display: 'flex', gap: '8px', alignItems: 'center' }}>
              <AlertCircle size={16} /> {actionError}
            </div>
          )}

          {/* Case Risk & Trust Overview Header */}
          <div className="card" style={{ borderColor: statusInfo.color, borderTopWidth: '4px' }}>
            <div className="card-inner" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <span style={{ fontSize: '11px', color: '#a1a1aa', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Financial Risk score</span>
                  <div style={{ fontSize: '32px', fontWeight: 700, color: '#f43f5e', marginTop: '4px' }}>{compositeRiskScore}%</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <span style={{ fontSize: '11px', color: '#a1a1aa', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Trust score</span>
                  <div style={{ fontSize: '32px', fontWeight: 700, color: '#10b981', marginTop: '4px' }}>{trustScore}%</div>
                </div>
                <div>
                  <span style={{ display: 'block', fontSize: '11px', color: '#a1a1aa', textTransform: 'uppercase', textAlign: 'center' }}>Workflow status</span>
                  <div style={{ 
                    display: 'flex', alignItems: 'center', gap: '6px', marginTop: '6px',
                    padding: '4px 10px', background: `${statusInfo.color}15`, 
                    color: statusInfo.color, borderRadius: '4px', fontWeight: 700, fontSize: '12px'
                  }}>
                    {statusInfo.icon} {statusBadge}
                  </div>
                </div>
              </div>

              {/* Subscores Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px', borderTop: '1px solid #27272a', paddingTop: '12px', marginTop: '4px', fontSize: '11px', color: '#a1a1aa' }}>
                <div>
                  Identity Match
                  <div style={{ color: '#fff', fontWeight: 600, fontSize: '13px', marginTop: '2px' }}>{caseDetails.trust_score?.sub_scores?.identity || 100}%</div>
                </div>
                <div>
                  Financial Audit
                  <div style={{ color: '#fff', fontWeight: 600, fontSize: '13px', marginTop: '2px' }}>{caseDetails.trust_score?.sub_scores?.financial || 100}%</div>
                </div>
                <div>
                  Tamper Forensics
                  <div style={{ color: '#fff', fontWeight: 600, fontSize: '13px', marginTop: '2px' }}>{100 - (caseDetails.risk_score?.sub_scores?.tampering || 0)}%</div>
                </div>
                <div>
                  Metadata Integrity
                  <div style={{ color: '#fff', fontWeight: 600, fontSize: '13px', marginTop: '2px' }}>{100 - (caseDetails.risk_score?.sub_scores?.metadata || 0)}%</div>
                </div>
              </div>
            </div>
          </div>

          {/* Tab Navigation for Detailed Case Info */}
          <div style={{ display: 'flex', borderBottom: '1px solid #27272a', gap: '16px' }}>
            {[
              { id: 'overview', label: 'Overview & Narrative' },
              { id: 'inconsistencies', label: `Inconsistency Ledger (${detectedIssues.length})` },
              { id: 'visual_vit', label: 'ViT / OCR Scan' },
              { id: 'chat_assistant', label: 'Reasoning Chat' }
            ].map(t => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                style={{
                  padding: '8px 0',
                  background: 'transparent',
                  border: 'none',
                  borderBottom: activeTab === t.id ? '2px solid #3b82f6' : '2px solid transparent',
                  color: activeTab === t.id ? '#fff' : '#a1a1aa',
                  cursor: 'pointer',
                  fontSize: '13px',
                  fontWeight: 600,
                  transition: 'all 0.15s'
                }}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* TAB 1: OVERVIEW & NARRATIVE */}
          {activeTab === 'overview' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div className="card" style={{ background: 'linear-gradient(to right, #18181b, #0c0a09)' }}>
                <div className="card-inner" style={{ padding: '16px' }}>
                  <div style={{ fontSize: '14px', fontWeight: 600, color: '#3b82f6', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Shield size={15} /> LLM Case-Level Narrative
                  </div>
                  <div style={{ color: '#e4e4e7', fontSize: '14px', lineHeight: 1.6 }}>
                    {execSummary || "No executive summary available."}
                  </div>
                  {caseDetails.explanation?.narrative && (
                    <div style={{ color: '#a1a1aa', fontSize: '13px', lineHeight: 1.5, marginTop: '12px', paddingTop: '12px', borderTop: '1px solid rgba(255,255,255,0.05)', whiteSpace: 'pre-wrap' }}>
                      {caseDetails.explanation.narrative}
                    </div>
                  )}
                </div>
              </div>

              {/* Case Notes & Audit Logs */}
              <div className="card">
                <div className="card-inner" style={{ padding: '16px' }}>
                  <div style={{ fontSize: '14px', fontWeight: 600, color: '#fff', marginBottom: '12px' }}>Case History & Comments</div>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '200px', overflowY: 'auto', marginBottom: '12px' }}>
                    {caseDetails.notes?.length === 0 ? (
                      <div style={{ color: '#71717a', fontSize: '12px', fontStyle: 'italic' }}>No investigator comments logged.</div>
                    ) : (
                      caseDetails.notes?.map((n, i) => (
                        <div key={i} style={{ background: '#18181b', padding: '10px', borderRadius: '6px', fontSize: '12.5px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', color: '#a1a1aa', fontSize: '11px', marginBottom: '4px' }}>
                            <strong>{n.username} ({n.role})</strong>
                            <span>{new Date(n.created_at || n.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                          </div>
                          <div style={{ color: '#f4f4f5' }}>{n.text || n.note}</div>
                        </div>
                      ))
                    )}
                  </div>

                  {role !== 'Compliance Auditor' && (
                    <form onSubmit={handleAddNote} style={{ display: 'flex', gap: '8px' }}>
                      <input 
                        type="text" 
                        placeholder="Add internal investigator comment..." 
                        value={noteText}
                        onChange={(e) => setNoteText(e.target.value)}
                        style={{
                          flex: 1,
                          background: '#09090b',
                          border: '1px solid #27272a',
                          borderRadius: '6px',
                          padding: '8px 12px',
                          color: '#fff',
                          fontSize: '13px',
                          outline: 'none'
                        }}
                      />
                      <button type="submit" disabled={isSubmittingNote} className="btn btn-ghost" style={{ padding: '8px 14px', fontSize: '13px', border: '1px solid #27272a' }}>
                        Post
                      </button>
                    </form>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: INCONSISTENCY LEDGER */}
          {activeTab === 'inconsistencies' && (
            <div className="card">
              <div className="card-inner" style={{ padding: '16px' }}>
                <div style={{ fontSize: '14px', fontWeight: 600, color: '#fff', marginBottom: '12px', display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <AlertTriangle size={15} color="#f43f5e" /> Audit Ledger & Tampering Detections
                </div>
                
                {detectedIssues.length === 0 ? (
                  <div style={{ padding: '24px', textAlign: 'center', color: '#71717a', fontSize: '13px' }}>
                    🎉 No anomalies or business fraud inconsistencies detected in this case.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {detectedIssues.map((issue, idx) => {
                      const sevColor = issue.severity === 'Critical' ? '#be123c' : issue.severity === 'High' ? '#f43f5e' : issue.severity === 'Medium' ? '#f97316' : '#eab308';
                      const isSelected = selectedIssueIndex === idx;
                      const isCrossDoc = issue.issue?.toLowerCase()?.includes('cross-document') || issue.issue?.toLowerCase()?.includes('inconsistency');
                      
                      return (
                        <div 
                          key={idx}
                          onClick={() => {
                            setSelectedIssueIndex(isSelected ? null : idx);
                            if (issue.page !== undefined) setCurrentPage(issue.page);
                          }}
                          style={{
                            background: isSelected ? 'rgba(59, 130, 246, 0.04)' : '#18181b',
                            borderLeft: `4px solid ${sevColor}`,
                            border: isSelected ? '1px solid #3b82f640' : 'none',
                            padding: '12px',
                            borderRadius: '4px',
                            cursor: 'pointer',
                            transition: 'all 0.15s'
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                            <span style={{ fontSize: '13px', fontWeight: 600, color: isCrossDoc ? '#60a5fa' : '#fff' }}>
                              {issue.issue}
                            </span>
                            <span style={{ background: `${sevColor}15`, color: sevColor, padding: '2px 6px', borderRadius: '4px', fontSize: '10px', fontWeight: 700 }}>
                              {issue.severity.toUpperCase()}
                            </span>
                          </div>
                          <p style={{ margin: 0, fontSize: '12px', color: '#a1a1aa', lineHeight: 1.4 }}>
                            {issue.description || 'Audit indicator flagged during validation.'}
                          </p>
                          {issue.recommendation && (
                            <div style={{ marginTop: '8px', fontSize: '11px', color: '#34d399', background: 'rgba(52, 211, 153, 0.05)', padding: '4px 8px', borderRadius: '4px' }}>
                              <strong>Recommendation:</strong> {issue.recommendation}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 3: VIT / OCR SCAN */}
          {activeTab === 'visual_vit' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* ViT heuristics */}
              <div className="card">
                <div className="card-inner" style={{ padding: '16px' }}>
                  <div style={{ fontSize: '14px', fontWeight: 600, color: '#3b82f6', marginBottom: '12px', display: 'flex', gap: '6px', alignItems: 'center' }}>
                    <FileCheck size={15} /> Vision Transformer LayoutLMv3 Analysis
                  </div>
                  
                  {activeAnalysis?.results?.tampering ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #27272a', paddingBottom: '6px' }}>
                        <span style={{ color: '#a1a1aa' }}>Visual Layout Verdict:</span>
                        <span style={{ fontWeight: 600, color: activeAnalysis.results.tampering.verdict === 'clean' ? '#10b981' : '#f43f5e' }}>
                          {activeAnalysis.results.tampering.verdict?.toUpperCase()}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #27272a', paddingBottom: '6px' }}>
                        <span style={{ color: '#a1a1aa' }}>Composite Tampering Score:</span>
                        <span>{activeAnalysis.results.tampering.composite_score || 0}/100</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #27272a', paddingBottom: '6px' }}>
                        <span style={{ color: '#a1a1aa' }}>Copy-Move Forgeries:</span>
                        <span>{activeAnalysis.results.tampering.copy_move?.detected ? 'DETECTED' : 'CLEAN'}</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: '#a1a1aa' }}>Metadata Software fields:</span>
                        <span style={{ color: '#f59e0b' }}>{activeAnalysis.results.metadata?.raw_metadata?.software || 'Unmarked/Clean'}</span>
                      </div>
                    </div>
                  ) : (
                    <div style={{ color: '#a1a1aa', fontSize: '12.5px', fontStyle: 'italic', textAlign: 'center' }}>
                      Select a document tab on the left to review its Vision Transformer analysis.
                    </div>
                  )}
                </div>
              </div>

              {/* OCR Structured Fields */}
              <div className="card">
                <div className="card-inner" style={{ padding: '16px' }}>
                  <button
                    onClick={() => setOcrOpen(!ocrOpen)}
                    style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'transparent', border: 'none', color: '#fff', fontSize: '14px', fontWeight: 600, padding: 0, cursor: 'pointer' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><Database size={15} /> OCR Structured Fields</div>
                    {ocrOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>

                  {ocrOpen && activeAnalysis?.results?.ocr && (
                    <div style={{ marginTop: '12px' }}>
                      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid #27272a', paddingBottom: '6px', marginBottom: '10px' }}>
                        <button onClick={() => setOcrViewMode('structured')} style={{ fontSize: '11px', background: ocrViewMode === 'structured' ? '#27272a' : 'transparent', border: 'none', padding: '4px 10px', borderRadius: '4px', cursor: 'pointer', color: ocrViewMode === 'structured' ? '#fff' : '#a1a1aa' }}>Structured Fields</button>
                        <button onClick={() => setOcrViewMode('raw')} style={{ fontSize: '11px', background: ocrViewMode === 'raw' ? '#27272a' : 'transparent', border: 'none', padding: '4px 10px', borderRadius: '4px', cursor: 'pointer', color: ocrViewMode === 'raw' ? '#fff' : '#a1a1aa' }}>Raw OCR Text</button>
                      </div>

                      {ocrViewMode === 'structured' ? (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '8px', background: '#09090b', padding: '10px', borderRadius: '6px', border: '1px solid #27272a', fontSize: '12px' }}>
                          {Object.entries(activeAnalysis.results.ocr.structured_data || {})
                            .filter(([key]) => key !== 'transactions')
                            .map(([key, rawValue]) => {
                              const name = key.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                              const displayVal = (rawValue && typeof rawValue === 'object' && 'value' in rawValue) ? rawValue.value : rawValue;
                              return (
                                <div key={key} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #1c1c1e', paddingBottom: '4px' }}>
                                  <span style={{ color: '#a1a1aa' }}>{name}</span>
                                  <span style={{ color: '#fff', fontWeight: 600 }}>{String(displayVal || 'N/A')}</span>
                                </div>
                              );
                            })}
                        </div>
                      ) : (
                        <div style={{ background: '#09090b', padding: '10px', borderRadius: '4px', border: '1px solid #27272a', maxHeight: '180px', overflowY: 'auto' }}>
                          <pre style={{ margin: 0, fontSize: '11px', color: '#a1a1aa', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'monospace' }}>
                            {activeAnalysis.results.ocr.extraction?.full_text || 'No text extracted.'}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: REASONING CHAT */}
          {activeTab === 'chat_assistant' && (
            <div className="card" style={{ display: 'flex', flexDirection: 'column', height: '350px' }}>
              <div className="card-inner" style={{ padding: '12px', display: 'flex', flexDirection: 'column', height: '100%' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#3b82f6', marginBottom: '8px', display: 'flex', gap: '6px', alignItems: 'center' }}>
                  <MessageSquare size={14} /> Explainable AI (XAI) Chat Window
                </div>

                <div style={{ flex: 1, overflowY: 'auto', background: '#09090b', padding: '10px', borderRadius: '6px', border: '1px solid #27272a', marginBottom: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {chatHistory.map((msg, i) => (
                    <div 
                      key={i} 
                      style={{
                        alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                        background: msg.role === 'user' ? '#3b82f6' : '#18181b',
                        color: '#fff',
                        padding: '8px 12px',
                        borderRadius: '12px',
                        fontSize: '12.5px',
                        maxWidth: '85%'
                      }}
                    >
                      {msg.text}
                    </div>
                  ))}
                  {isAsking && (
                    <div style={{ alignSelf: 'flex-start', background: '#18181b', color: '#a1a1aa', padding: '8px 12px', borderRadius: '12px', fontSize: '12px', fontStyle: 'italic' }}>
                      SecureDocXAI is thinking...
                    </div>
                  )}
                </div>

                <form onSubmit={handleAskChat} style={{ display: 'flex', gap: '6px' }}>
                  <input
                    type="text"
                    placeholder="Ask reasoning engine (e.g. Is IFSC code valid?)..."
                    value={chatQuestion}
                    onChange={(e) => setChatQuestion(e.target.value)}
                    style={{
                      flex: 1,
                      background: '#09090b',
                      border: '1px solid #27272a',
                      borderRadius: '6px',
                      padding: '8px 12px',
                      color: '#fff',
                      fontSize: '12.5px',
                      outline: 'none'
                    }}
                  />
                  <button type="submit" disabled={isAsking} className="btn btn-primary" style={{ padding: '8px 12px', borderRadius: '6px' }}>
                    <Send size={14} />
                  </button>
                </form>
              </div>
            </div>
          )}

          {/* Workflow Actions Panel */}
          {role !== 'Compliance Auditor' && (
            <div className="card" id="decision-section-anchor" style={{ background: 'rgba(255,255,255,0.01)', borderStyle: 'dashed' }}>
              <div className="card-inner" style={{ padding: '16px' }}>
                <div style={{ fontSize: '14px', fontWeight: 600, color: '#fff', marginBottom: '12px' }}>Resolution Center</div>
                
                {/* Assign to me */}
                {!caseDetails.assigned_analyst && (role === 'Fraud Analyst' || role === 'System Admin') && (
                  <button className="btn btn-primary w-full" onClick={handleAssignToMe} style={{ marginBottom: '12px', width: '100%' }}>
                    Assign Case to Me
                  </button>
                )}

                {/* Manager Decision workflow */}
                {(role === 'Branch Manager' || role === 'System Admin') ? (
                  <form onSubmit={handleDecision} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <select 
                        value={decisionType}
                        onChange={(e) => setDecisionType(e.target.value)}
                        style={{
                          background: '#09090b',
                          border: '1px solid #27272a',
                          borderRadius: '6px',
                          padding: '8px 12px',
                          color: '#fff',
                          fontSize: '13px'
                        }}
                      >
                        <option value="APPROVED">APPROVE APPLICATION</option>
                        <option value="REJECTED">REJECT FRAUD CASE</option>
                        <option value="CLOSED">RESOLVE / CLOSE CASE</option>
                      </select>
                    </div>

                    {decisionType === 'APPROVED' && caseDetails.priority === 'CRITICAL' && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', background: 'rgba(244,63,94,0.08)', border: '1px solid rgba(244,63,94,0.2)', padding: '10px', borderRadius: '6px' }}>
                        <span style={{ fontSize: '11px', color: '#f43f5e', fontWeight: 700 }}>⚠️ SECURITY PROTOCOL FOR CRITICAL OVERRIDES:</span>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: '#e4e4e7', cursor: 'pointer' }}>
                          <input 
                            type="checkbox" 
                            checked={explicitConfirmation}
                            onChange={(e) => setExplicitConfirmation(e.target.checked)}
                          />
                          I explicitly confirm CPF audit verification override.
                        </label>
                      </div>
                    )}

                    <textarea
                      placeholder="Provide detailed justification/override notes..."
                      value={decisionComment}
                      onChange={(e) => setDecisionComment(e.target.value)}
                      required
                      style={{
                        background: '#09090b',
                        border: '1px solid #27272a',
                        borderRadius: '6px',
                        padding: '10px',
                        color: '#fff',
                        fontSize: '13px',
                        minHeight: '80px',
                        outline: 'none'
                      }}
                    />

                    <button type="submit" disabled={isSubmittingDecision} className="btn btn-primary" style={{ width: '100%' }}>
                      {isSubmittingDecision ? 'Submitting decision...' : 'Commit Decision'}
                    </button>
                  </form>
                ) : (
                  /* Fraud Analyst actions */
                  (role === 'Fraud Analyst' || role === 'System Admin') && caseDetails.assigned_analyst === currentUser.username && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                        <button className="btn" style={{ background: '#10b981', color: '#fff', fontSize: '12px', padding: '8px 12px' }} onClick={() => handleMarkSafe(prompt('Justification for marking safe:') || '')}>
                          Mark Safe
                        </button>
                        <button className="btn" style={{ background: '#f43f5e', color: '#fff', fontSize: '12px', padding: '8px 12px' }} onClick={() => handleRejectCase(prompt('Reason for analyst rejection:') || '')}>
                          Reject Case
                        </button>
                      </div>
                      <button className="btn btn-ghost" style={{ border: '1px solid #f97316', color: '#f97316', fontSize: '12px', padding: '8px 12px' }} onClick={() => handleEscalateCase(prompt('Escalation reason:') || '')}>
                        Escalate Case to Manager
                      </button>
                    </div>
                  )
                )}
              </div>
            </div>
          )}

        </div>

      </div>
    </div>
  );
};

export default DocumentInsights;
