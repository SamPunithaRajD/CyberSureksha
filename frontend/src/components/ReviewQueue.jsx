import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { Search, Filter, ShieldAlert, CheckCircle, Clock, AlertTriangle, ArrowRight, Eye } from 'lucide-react';

const ReviewQueue = ({ currentUser, onViewDocument }) => {
  const [filter, setFilter] = useState('ALL'); // ALL, FLAGGED, CLEAN
  const [searchTerm, setSearchTerm] = useState('');

  const { data: rawCasesData, isLoading } = useQuery({
    queryKey: ['cases', 'list'],
    queryFn: async () => {
      const res = await axios.get('http://localhost:8000/api/v1/cases/?per_page=50');
      return res.data.cases || [];
    },
    refetchInterval: 3000,
  });

  const queueData = React.useMemo(() => {
    if (!rawCasesData) return [];
    return rawCasesData.map(caseItem => ({
      analysis_id: caseItem.id,
      document_id: caseItem.document_ids?.[0] || '',
      document_name: caseItem.case_name || 'Investigation Case',
      workflow_status: caseItem.status || 'UNASSIGNED',
      risk_tier: caseItem.risk_score?.category === 'Critical' ? 'rejected' : caseItem.risk_score?.category === 'High' ? 'high_risk' : caseItem.risk_score?.category === 'Medium' ? 'review' : 'low_risk',
      risk_score: caseItem.risk_score?.composite || 0.0,
      priority: caseItem.priority || 'LOW',
      branch: caseItem.branch || 'Global Branch',
      uploaded_by: caseItem.uploaded_by || 'system',
      created_at: caseItem.created_at,
      processing_time_ms: 850
    }));
  }, [rawCasesData]);

  const getFilteredData = () => {
    if (!queueData) return [];
    
    return queueData.filter(item => {
      // Status Filter
      if (filter === 'FLAGGED' && (item.workflow_status === 'APPROVED' || item.workflow_status === 'REJECTED')) return false;
      if (filter === 'CLEAN' && (item.workflow_status === 'UNASSIGNED' || item.workflow_status === 'UNDER_REVIEW' || item.workflow_status === 'ESCALATED')) return false;
      
      // Search Filter
      if (searchTerm) {
        const searchLower = searchTerm.toLowerCase();
        const docName = (item.document_name || '').toLowerCase();
        const docId = (item.document_id || '').toLowerCase();
        const docBranch = (item.branch || '').toLowerCase();
        if (!docName.includes(searchLower) && !docId.includes(searchLower) && !docBranch.includes(searchLower)) {
          return false;
        }
      }
      return true;
    });
  };

  const getPriority = (priorityValue) => {
    switch (priorityValue) {
      case 'CRITICAL':
        return { label: 'CRITICAL', color: '#f43f5e', bg: 'rgba(244,63,94,0.12)' };
      case 'HIGH':
        return { label: 'HIGH', color: '#f97316', bg: 'rgba(249,115,22,0.12)' };
      case 'MEDIUM':
        return { label: 'MEDIUM', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' };
      case 'LOW':
      default:
        return { label: 'LOW', color: '#10b981', bg: 'rgba(16,185,129,0.12)' };
    }
  };

  const getSLATimer = (tier) => {
    if (tier === 'high_risk' || tier === 'rejected') return '5h 02m';
    if (tier === 'review') return '2h 14m';
    return '12h 00m';
  };

  const getBadgeStyle = (statusVal, tier) => {
    const s = (statusVal || '').toUpperCase();
    if (s === 'APPROVED') {
      return { bg: 'rgba(16,185,129,0.12)', col: '#10b981', icon: <CheckCircle size={14} /> };
    }
    if (s === 'REJECTED') {
      return { bg: 'rgba(244,63,94,0.12)', col: '#f43f5e', icon: <ShieldAlert size={14} /> };
    }
    if (s === 'ESCALATED') {
      return { bg: 'rgba(249,115,22,0.12)', col: '#f97316', icon: <AlertTriangle size={14} /> };
    }
    if (s === 'UNDER_REVIEW') {
      return { bg: 'rgba(245,158,11,0.12)', col: '#f59e0b', icon: <Clock size={14} /> };
    }
    if (s === 'SAFE_TO_PROCESS' || s === 'CLOSED') {
      return { bg: 'rgba(16,185,129,0.12)', col: '#10b981', icon: <CheckCircle size={14} /> };
    }
    if (s === 'WAITLISTED' || s === 'WAITLIST') {
      return { bg: 'rgba(245,158,11,0.12)', col: '#f59e0b', icon: <Clock size={14} /> };
    }
    // Fallback to tier
    switch (tier) {
      case 'rejected':
      case 'high_risk': 
        return { bg: 'rgba(244,63,94,0.12)', col: '#f43f5e', icon: <ShieldAlert size={14} /> };
      case 'review': 
        return { bg: 'rgba(245,158,11,0.12)', col: '#f59e0b', icon: <Clock size={14} /> };
      case 'low_risk':
      case 'safe_to_process': 
        return { bg: 'rgba(59,130,246,0.12)', col: '#3b82f6', icon: <CheckCircle size={14} /> };
      case 'verified': 
        return { bg: 'rgba(16,185,129,0.12)', col: '#10b981', icon: <CheckCircle size={14} /> };
      default: 
        return { bg: 'rgba(161,161,170,0.12)', col: '#a1a1aa', icon: <Clock size={14} /> };
    }
  };

  const getEmptyStateMessage = () => {
    const role = currentUser?.role;
    if (role === 'Underwriting Officer') return 'No applications submitted yet. Click Upload to start.';
    if (role === 'Fraud Analyst') return 'No active fraud investigations assigned.';
    if (role === 'Branch Manager') return 'No applications pending approval.';
    if (role === 'Compliance Auditor') return 'No compliance violations detected.';
    return 'No documents found matching the current filters.';
  };

  const filteredData = getFilteredData();
  const role = currentUser?.role;

  return (
    <div className="content" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 65px)', overflow: 'hidden' }}>
      <div className="section-header" style={{ marginBottom: '20px' }}>
        <div>
          <div className="section-title">
            {role === 'Underwriting Officer' && "Underwriting Applications"}
            {role === 'Fraud Analyst' && "Active Investigation Tickets"}
            {role === 'Branch Manager' && "Pending Branch Approvals"}
            {role === 'Compliance Auditor' && "Compliance Audit Ledger"}
            {role === 'System Admin' && "Global Core Processing Queue"}
          </div>
          <div className="section-sub">
            {role === 'Underwriting Officer' && "Manage and track document uploads and verification queues."}
            {role === 'Fraud Analyst' && "Examine flagged documents, analyze OCR outputs, and resolve cases."}
            {role === 'Branch Manager' && "Approve or reject customer files containing critical risk profiles."}
            {role === 'Compliance Auditor' && "Read-only access to all verified records, decisions, and system overrides."}
            {role === 'System Admin' && "Platform logs of all active scans, users, and server workloads."}
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: '12px' }}>
          <div className="search-bar" style={{ width: '250px' }}>
            <Search size={14} className="text-muted" />
            <input 
              type="text" 
              placeholder="Search ID, Branch or Name..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          
          <div style={{ display: 'flex', background: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '4px' }}>
            {['ALL', 'FLAGGED', 'CLEAN'].map(f => (
              <button 
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  padding: '4px 12px',
                  fontSize: '12px',
                  fontWeight: 500,
                  borderRadius: '4px',
                  background: filter === f ? '#27272a' : 'transparent',
                  color: filter === f ? '#fff' : '#a1a1aa',
                  border: 'none',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div className="card-inner" style={{ padding: 0, display: 'flex', flexDirection: 'column', height: '100%' }}>
          
          {/* DYNAMIC HEADER COLUMNS BY ROLE */}
          {role === 'Underwriting Officer' && (
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr', padding: '16px 24px', borderBottom: '1px solid #27272a', fontSize: '12px', color: '#a1a1aa', fontWeight: 500, background: 'rgba(0,0,0,0.2)' }}>
              <div>DOCUMENT NAME</div>
              <div>APPLICATION ID</div>
              <div>UPLOAD STATUS</div>
              <div>VERIFICATION</div>
              <div>SUBMITTED AT</div>
            </div>
          )}

          {role === 'Fraud Analyst' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1.8fr 1fr 1fr 1fr 0.8fr 0.8fr', padding: '16px 24px', borderBottom: '1px solid #27272a', fontSize: '12px', color: '#a1a1aa', fontWeight: 500, background: 'rgba(0,0,0,0.2)' }}>
              <div>APPLICATION NAME</div>
              <div>INVESTIGATION ID</div>
              <div>PRIORITY</div>
              <div>SLA REMAINING</div>
              <div>RISK SCORE</div>
              <div>ACTIONS</div>
            </div>
          )}

          {role === 'Branch Manager' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1.8fr 1fr 1fr 1fr 1.2fr', padding: '16px 24px', borderBottom: '1px solid #27272a', fontSize: '12px', color: '#a1a1aa', fontWeight: 500, background: 'rgba(0,0,0,0.2)' }}>
              <div>APPLICANT FILE</div>
              <div>SUBMITTED BY</div>
              <div>BRANCH</div>
              <div>COMPOSITE RISK</div>
              <div>DECISION OVERRIDE</div>
            </div>
          )}

          {role === 'Compliance Auditor' && (
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1.2fr 1fr 1.2fr 1fr', padding: '16px 24px', borderBottom: '1px solid #27272a', fontSize: '12px', color: '#a1a1aa', fontWeight: 500, background: 'rgba(0,0,0,0.2)' }}>
              <div>EVENT RECORD</div>
              <div>OPERATOR</div>
              <div>SYSTEM TAG</div>
              <div>OVERRIDE REVIEW</div>
              <div>DATE</div>
            </div>
          )}

          {role === 'System Admin' && (
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1.2fr 1fr 1fr', padding: '16px 24px', borderBottom: '1px solid #27272a', fontSize: '12px', color: '#a1a1aa', fontWeight: 500, background: 'rgba(0,0,0,0.2)' }}>
              <div>SYSTEM REF</div>
              <div>UPLOADER</div>
              <div>SHIELD STATUS</div>
              <div>RISK CALC</div>
              <div>LATENCY</div>
            </div>
          )}
          
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {isLoading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#a1a1aa' }}>Loading queue data...</div>
            ) : filteredData.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#a1a1aa' }}>
                <div style={{ fontSize: '16px', marginBottom: '8px', fontWeight: 500 }}>Empty Queue</div>
                <div style={{ fontSize: '13px', color: '#71717a' }}>{getEmptyStateMessage()}</div>
              </div>
            ) : (
              filteredData.map((item, idx) => {
                const badge = getBadgeStyle(item.workflow_status, item.risk_tier);
                const priority = getPriority(item.priority);
                const sla = getSLATimer(item.risk_tier);
                
                // Highlight critical items visually
                const isCritical = priority.label === 'CRITICAL';
                const rowBorder = isCritical ? '1px solid rgba(244,63,94,0.3)' : '1px solid #27272a';
                const rowGlow = isCritical ? 'rgba(244,63,94,0.02)' : 'transparent';

                return (
                  <div 
                    key={item.analysis_id || idx} 
                    onClick={() => onViewDocument(item.analysis_id, item.document_id)}
                    style={{ 
                      display: 'grid', 
                      gridTemplateColumns: role === 'Fraud Analyst' ? '1.8fr 1fr 1fr 1fr 0.8fr 0.8fr' : role === 'Branch Manager' ? '1.8fr 1fr 1fr 1fr 1.2fr' : role === 'Compliance Auditor' ? '2fr 1.2fr 1fr 1.2fr 1fr' : role === 'System Admin' ? '2fr 1fr 1.2fr 1fr 1fr' : '2fr 1fr 1fr 1fr 1fr',
                      padding: '16px 24px', 
                      borderBottom: rowBorder,
                      alignItems: 'center',
                      cursor: 'pointer',
                      background: rowGlow,
                      transition: 'background 0.2s',
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                    onMouseLeave={(e) => e.currentTarget.style.background = rowGlow}
                  >
                    
                    {/* UNDERWRITER ROW RENDER */}
                    {role === 'Underwriting Officer' && (
                      <>
                        <div style={{ fontWeight: 500, color: '#fff', display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: badge.col }}></div>
                          {item.document_name || `Unknown File`}
                        </div>
                        <div style={{ color: '#a1a1aa', fontSize: '13px', fontFamily: 'monospace' }}>
                          App-{item.document_id ? item.document_id.substring(0, 6) : 'Unknown'}
                        </div>
                        <div style={{ color: item.workflow_status === 'APPROVED' ? '#10b981' : item.workflow_status === 'REJECTED' ? '#f43f5e' : '#f59e0b', fontWeight: 500 }}>
                          {item.workflow_status ? item.workflow_status.replace('_', ' ') : 'UNASSIGNED'}
                        </div>
                        <div>
                          <div style={{ 
                            display: 'inline-flex', 
                            alignItems: 'center', 
                            gap: '6px',
                            background: badge.bg, 
                            color: badge.col, 
                            padding: '4px 10px', 
                            borderRadius: '20px', 
                            fontSize: '11px',
                            fontWeight: 600
                          }}>
                            {badge.icon} {item.workflow_status ? item.workflow_status.replace('_', ' ').toUpperCase() : (item.risk_tier ? item.risk_tier.replace('_', ' ').toUpperCase() : 'UNKNOWN')}
                          </div>
                        </div>
                        <div style={{ color: '#a1a1aa', fontSize: '13px' }}>
                          {new Date(item.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
                        </div>
                      </>
                    )}

                    {/* FRAUD ANALYST ROW RENDER */}
                    {role === 'Fraud Analyst' && (
                      <>
                        <div style={{ fontWeight: 500, color: '#fff', display: 'flex', alignItems: 'center', gap: '8px' }}>
                          {isCritical && <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#f43f5e', boxShadow: '0 0 8px #f43f5e', display: 'inline-block', marginRight: '4px' }}></span>}
                          {item.document_name || `Unknown File`}
                        </div>
                        <div style={{ color: '#a1a1aa', fontSize: '13px', fontFamily: 'monospace' }}>
                          DSA-{item.document_id ? item.document_id.substring(0, 6) : 'Unknown'}
                        </div>
                        <div>
                          <span style={{ background: priority.bg, color: priority.color, padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>
                            {priority.label}
                          </span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: isCritical ? '#f43f5e' : '#a1a1aa', fontSize: '13px' }}>
                          <Clock size={12} /> {sla}
                        </div>
                        <div>
                          <span style={{ color: item.risk_score > 70 ? '#f43f5e' : item.risk_score > 40 ? '#f59e0b' : '#10b981', fontWeight: 600 }}>
                            {Math.round(item.risk_score)}
                          </span>
                          <span style={{ color: '#52525b', fontSize: '12px' }}>/100</span>
                        </div>
                        <div style={{ display: 'flex', gap: '4px' }}>
                          <button className="icon-btn" title="Inspect" style={{ padding: '6px' }}>
                            <Eye size={14} />
                          </button>
                        </div>
                      </>
                    )}

                    {/* BRANCH MANAGER ROW RENDER */}
                    {role === 'Branch Manager' && (
                      <>
                        <div style={{ fontWeight: 500, color: '#fff' }}>
                          {item.document_name || `Unknown File`}
                        </div>
                        <div style={{ color: '#a1a1aa', fontSize: '13px' }}>
                          {item.uploaded_by || 'system'}
                        </div>
                        <div style={{ color: '#a1a1aa', fontSize: '13px' }}>
                          {item.branch || 'Canara Bank'}
                        </div>
                        <div>
                          <span style={{ color: item.risk_score > 70 ? '#f43f5e' : item.risk_score > 40 ? '#f59e0b' : '#10b981', fontWeight: 600 }}>
                            {Math.round(item.risk_score)}
                          </span>
                          <span style={{ color: '#52525b', fontSize: '12px' }}>/100</span>
                        </div>
                        <div>
                          {item.risk_tier === 'high_risk' || item.risk_tier === 'rejected' ? (
                            <span style={{ color: '#f43f5e', background: 'rgba(244,63,94,0.1)', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>OVERRIDE REQUIRED</span>
                          ) : (
                            <span style={{ color: '#10b981', background: 'rgba(16,185,129,0.1)', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>SAFE RUN</span>
                          )}
                        </div>
                      </>
                    )}

                    {/* COMPLIANCE AUDITOR ROW RENDER */}
                    {role === 'Compliance Auditor' && (
                      <>
                        <div style={{ fontWeight: 500, color: '#fff' }}>
                          Audit event for {item.document_name || `Unknown File`}
                        </div>
                        <div style={{ color: '#a1a1aa', fontSize: '13px' }}>
                          {item.uploaded_by || 'system'}
                        </div>
                        <div style={{ color: '#a1a1aa', fontSize: '13px' }}>
                          {item.branch || 'Canara Bank'}
                        </div>
                        <div>
                          {item.risk_tier === 'high_risk' || item.risk_tier === 'rejected' ? (
                            <span style={{ color: '#f97316', background: 'rgba(249,115,22,0.1)', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>REVIEWED OVERRIDE</span>
                          ) : (
                            <span style={{ color: '#10b981', background: 'rgba(16,185,129,0.1)', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>REGULATORY COMPLIANT</span>
                          )}
                        </div>
                        <div style={{ color: '#a1a1aa', fontSize: '13px' }}>
                          {new Date(item.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                        </div>
                      </>
                    )}

                    {/* SYSTEM ADMIN ROW RENDER */}
                    {role === 'System Admin' && (
                      <>
                        <div style={{ fontWeight: 500, color: '#fff', fontFamily: 'monospace', fontSize: '13px' }}>
                          SYS-DSA-{item.document_id ? item.document_id.substring(0, 8) : 'Unknown'}
                        </div>
                        <div style={{ color: '#a1a1aa', fontSize: '13px' }}>
                          {item.uploaded_by || 'system'}
                        </div>
                        <div style={{ 
                          display: 'inline-flex', 
                          alignItems: 'center', 
                          gap: '6px',
                          background: badge.bg, 
                          color: badge.col, 
                          padding: '2px 8px', 
                          borderRadius: '4px', 
                          fontSize: '11px',
                          fontWeight: 600
                        }}>
                          {item.risk_tier ? item.risk_tier.toUpperCase() : 'UNKNOWN'}
                        </div>
                        <div>
                          <span style={{ color: item.risk_score > 70 ? '#f43f5e' : item.risk_score > 40 ? '#f59e0b' : '#10b981', fontWeight: 600 }}>
                            {Math.round(item.risk_score)}%
                          </span>
                        </div>
                        <div style={{ color: '#3b82f6', fontSize: '13px', fontWeight: 600 }}>
                          {item.processing_time_ms ? `${item.processing_time_ms}ms` : '850ms'}
                        </div>
                      </>
                    )}

                  </div>
                )
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReviewQueue;
