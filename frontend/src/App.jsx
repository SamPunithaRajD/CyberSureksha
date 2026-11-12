import React, { useState, useEffect } from 'react';
import { Search, Bell, RefreshCw, Upload, CheckCircle, Check, ShieldAlert, Shield, Clock, AlertTriangle } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import UploadModal from './components/UploadModal';

import ReviewQueue from './components/ReviewQueue';
import DocumentInsights from './components/DocumentInsights';
import Login from './components/Login';
import ComplianceLogs from './components/ComplianceLogs';

const App = () => {
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [toast, setToast] = useState({ visible: false, message: '', type: 'info' });
  const [showScanOverlay, setShowScanOverlay] = useState(true);
  
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [currentUser, setCurrentUser] = useState(JSON.parse(localStorage.getItem('user')) || null);

  // One-time lifecycle reset check for v2 stability
  useEffect(() => {
    const isReset = localStorage.getItem('lifecycle_reset_v2');
    if (!isReset) {
      localStorage.removeItem('selectedDocumentId');
      localStorage.removeItem('selectedAnalysisId');
      localStorage.removeItem('selectedIssueIndex');
      localStorage.setItem('lifecycle_reset_v2', 'true');
    }
  }, []);

  const getInitialView = (user) => {
    if (!user) return 'dashboard';
    if (user.role === 'Underwriting Officer') return 'queue';
    if (user.role === 'Fraud Analyst') return 'queue';
    if (user.role === 'Branch Manager') return 'queue';
    if (user.role === 'Compliance Auditor') return 'compliance';
    if (user.role === 'System Admin') return 'dashboard';
    return 'dashboard';
  };

  // Navigation State
  const [currentView, setCurrentView] = useState(() => {
    const saved = localStorage.getItem('currentView');
    if (saved) return saved;
    const user = JSON.parse(localStorage.getItem('user')) || null;
    return getInitialView(user);
  });

  useEffect(() => {
    localStorage.setItem('currentView', currentView);
  }, [currentView]);

  useEffect(() => {
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    }
  }, [token]);

  const handleLoginSuccess = (newToken, user) => {
    setToken(newToken);
    setCurrentUser(user);
    showToastMsg(`Logged in as ${user.username}`, 'success');
    setCurrentView(getInitialView(user));
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('currentView');
    localStorage.removeItem('selectedDocumentId');
    localStorage.removeItem('selectedAnalysisId');
    localStorage.removeItem('selectedIssueIndex');
    delete axios.defaults.headers.common['Authorization'];
    setToken('');
    setCurrentUser(null);
    setCurrentView('dashboard');
    showToastMsg('Logged out successfully', 'info');
  };
  
  const [selectedDocumentId, setSelectedDocumentId] = useState(() => {
    const val = localStorage.getItem('selectedDocumentId');
    return (val && val !== 'null') ? val : null;
  });
  const [selectedAnalysisId, setSelectedAnalysisId] = useState(() => {
    const val = localStorage.getItem('selectedAnalysisId');
    return (val && val !== 'null') ? val : null;
  });

  useEffect(() => {
    if (selectedDocumentId) {
      localStorage.setItem('selectedDocumentId', selectedDocumentId);
    } else {
      localStorage.removeItem('selectedDocumentId');
    }
  }, [selectedDocumentId]);

  useEffect(() => {
    if (selectedAnalysisId) {
      localStorage.setItem('selectedAnalysisId', selectedAnalysisId);
    } else {
      localStorage.removeItem('selectedAnalysisId');
    }
  }, [selectedAnalysisId]);

  const queryClient = useQueryClient();

  // --- React Query Hooks for Live Data ---
  const { data: summaryData, refetch: refetchSummary } = useQuery({
    queryKey: ['dashboard', 'summary'],
    queryFn: async () => {
      const res = await axios.get('http://localhost:8000/api/v1/dashboard/summary');
      return res.data;
    },
    refetchInterval: 3000,
  });

  const { data: activityData, refetch: refetchActivity } = useQuery({
    queryKey: ['dashboard', 'recent-activity'],
    queryFn: async () => {
      const res = await axios.get('http://localhost:8000/api/v1/dashboard/recent-activity');
      return res.data.recent_activity;
    },
    refetchInterval: 3000,
  });

  const { data: trendsData } = useQuery({
    queryKey: ['dashboard', 'trends'],
    queryFn: async () => {
      const res = await axios.get('http://localhost:8000/api/v1/dashboard/trends');
      return res.data.trends;
    },
    refetchInterval: 10000,
  });

  const [activeAnalysis, setActiveAnalysis] = useState(null);
  const [activeDocument, setActiveDocument] = useState(null);

  const [showNotifications, setShowNotifications] = useState(false);

  // --- React Query for notifications ---
  const { data: notificationsData, refetch: refetchNotifications } = useQuery({
    queryKey: ['notifications'],
    queryFn: async () => {
      if (!token) return [];
      const res = await axios.get('http://localhost:8000/api/v1/notifications/');
      return res.data;
    },
    refetchInterval: 5000,
    enabled: !!token,
  });

  const handleMarkNotifRead = async (id, e) => {
    e.stopPropagation();
    try {
      await axios.post(`http://localhost:8000/api/v1/notifications/${id}/read`);
      refetchNotifications();
    } catch (err) {
      console.error("Failed to mark notification as read", err);
    }
  };

  const handleMarkAllNotifsRead = async () => {
    try {
      await axios.post('http://localhost:8000/api/v1/notifications/read-all');
      refetchNotifications();
    } catch (err) {
      console.error("Failed to mark all notifications as read", err);
    }
  };

  // Initial loading delay
  useEffect(() => {
    setTimeout(() => {
      setShowScanOverlay(false);
    }, 1500);
  }, []);

  const refreshDashboard = () => {
    refetchSummary();
    refetchActivity();
    showToastMsg('Dashboard refreshed', 'success');
  };

  const showToastMsg = (message, type = 'info') => {
    setToast({ visible: true, message, type });
    setTimeout(() => setToast({ visible: false, message: '', type: 'info' }), 3000);
  };

  const handleUploadComplete = ({ analysis, document }) => {
    // 1. Invalidate all dashboard + queue related queries
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });

    // 2. Set active document for the dashboard
    setActiveAnalysis(analysis);
    setActiveDocument(document);

    // 3. Redirect immediately to the insights/review page for the newly uploaded document
    const aid = analysis.id || analysis._id;
    const did = document.id || document._id;
    setSelectedAnalysisId(aid);
    setSelectedDocumentId(did);
    setCurrentView('insights');
    
    showToastMsg('Document analyzed successfully. Opening Report.', 'success');
  };

  // Fallbacks if no active scan yet
  const displayScore = activeAnalysis?.risk_score?.composite || 0;
  const displayTier = activeAnalysis?.risk_score?.tier?.toUpperCase() || 'CLEAN';
  const sub = activeAnalysis?.risk_score?.sub_scores || { metadata: 0, tampering: 0, signature: 0, amount: 0, anomaly: 0 };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div style={{ background: '#09090b', border: '1px solid #27272a', padding: '10px', borderRadius: '6px' }}>
          <p style={{ color: '#a1a1aa', fontSize: '12px', margin: 0 }}>{new Date(label).toLocaleDateString()}</p>
          <p style={{ color: '#3b82f6', fontSize: '14px', margin: '4px 0 0' }}>Scanned: {payload[0]?.value || 0}</p>
          <p style={{ color: '#f43f5e', fontSize: '14px', margin: '4px 0 0' }}>High Risk: {payload[1]?.value || 0}</p>
        </div>
      );
    }
    return null;
  };

  const gaugeCircumference = 2 * Math.PI * 74;
  const gaugeOffset = gaugeCircumference - (displayScore / 100) * gaugeCircumference;

  const notifications = notificationsData || [];
  const unreadCount = notifications.filter(n => !n.read).length;

  if (!token) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="app" style={{ position: 'relative', zIndex: 1 }}>
      {/* Background orbs */}
      <div className="bg-orbs">
        <div className="orb orb-1"></div>
        <div className="orb orb-2"></div>
        <div className="orb orb-3"></div>
      </div>

      {/* Loading scan overlay */}
      {showScanOverlay && (
        <div className="scan-overlay" style={{ transition: 'opacity 0.6s ease', opacity: showScanOverlay ? 1 : 0 }}>
          <div className="scan-ring">
            <div className="scan-logo">🛡</div>
          </div>
          <div className="scan-text">Initializing SecureDocXAI...</div>
          <div className="scan-bar"><div className="scan-progress"></div></div>
        </div>
      )}

      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-mark">SD</div>
          <div className="logo-text">SecureDocX<span>AI</span></div>
        </div>

        <div className="sidebar-section" style={{ marginTop: '16px' }}>
          <div className="sidebar-label">
            {currentUser?.role === 'Underwriting Officer' && "Underwriting Ops"}
            {currentUser?.role === 'Fraud Analyst' && "Fraud Investigations"}
            {currentUser?.role === 'Branch Manager' && "Branch Operations"}
            {currentUser?.role === 'Compliance Auditor' && "Compliance & Audit"}
            {currentUser?.role === 'System Admin' && "Platform Administration"}
          </div>

          {currentUser?.role === 'Underwriting Officer' && (
            <>
              <a className={`nav-item ${currentView === 'dashboard' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('dashboard'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="1" width="6" height="6" rx="1.5"/><rect x="9" y="1" width="6" height="6" rx="1.5"/><rect x="1" y="9" width="6" height="6" rx="1.5"/><rect x="9" y="9" width="6" height="6" rx="1.5"/></svg>
                Dashboard
              </a>
              <a className="nav-item" href="#" onClick={(e) => { e.preventDefault(); setIsUploadModalOpen(true); }}>
                <Upload className="nav-icon" size={14} />
                Upload Document
              </a>
              <a className={`nav-item ${currentView === 'queue' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('queue'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M2 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4zm2 0v8h8V4H4z"/></svg>
                Applications
              </a>
              <a className={`nav-item ${currentView === 'queue' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('queue'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg>
                Pending Reviews
              </a>
              <a className={`nav-item ${currentView === 'queue' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('queue'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 2a5 5 0 1 1 0 10A5 5 0 0 1 8 3z"/></svg>
                Upload History
              </a>
            </>
          )}

          {currentUser?.role === 'Fraud Analyst' && (
            <>
              <a className={`nav-item ${currentView === 'queue' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('queue'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M2 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4zm2 0v8h8V4H4z"/></svg>
                Investigation Queue
              </a>
              <a className={`nav-item ${currentView === 'queue' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('queue'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1l7 4v5c0 3.5-2.5 5.5-7 7-4.5-1.5-7-3.5-7-7V5L8 1z"/></svg>
                Flagged Documents
              </a>
              <a className="nav-item" href="#" onClick={(e) => { e.preventDefault(); showToastMsg('Fraud Explorer launched. Analysing document vectors...', 'success'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M2 2h12v10H2V2zm1 1v8h10V3H3zm2 2h6v1H5V5zm0 2h4v1H5V7z"/></svg>
                Fraud Explorer
              </a>
              <a className={`nav-item ${currentView === 'queue' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('queue'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14z"/></svg>
                Escalations
              </a>
              <a className={`nav-item ${currentView === 'queue' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('queue'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1z"/></svg>
                Internal Notes
              </a>
            </>
          )}

          {currentUser?.role === 'Branch Manager' && (
            <>
              <a className={`nav-item ${currentView === 'queue' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('queue'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M2 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4zm2 0v8h8V4H4z"/></svg>
                Approval Queue
              </a>
              <a className={`nav-item ${currentView === 'dashboard' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('dashboard'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="1" width="6" height="6" rx="1.5"/><rect x="9" y="1" width="6" height="6" rx="1.5"/><rect x="1" y="9" width="6" height="6" rx="1.5"/><rect x="9" y="9" width="6" height="6" rx="1.5"/></svg>
                Branch Metrics
              </a>
              <a className="nav-item" href="#" onClick={(e) => { e.preventDefault(); showToastMsg('Loading branch analyst workload distribution...', 'info'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg>
                Team Activity
              </a>
              <a className="nav-item" href="#" onClick={(e) => { e.preventDefault(); showToastMsg('Exporting branch fraud reports...', 'success'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1z"/></svg>
                Fraud Reports
              </a>
            </>
          )}

          {currentUser?.role === 'Compliance Auditor' && (
            <>
              <a className={`nav-item ${currentView === 'compliance' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('compliance'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0z"/></svg>
                Compliance Logs
              </a>
              <a className={`nav-item ${currentView === 'compliance' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('compliance'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M2 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4zm2 0v8h8V4H4z"/></svg>
                Audit History
              </a>
              <a className={`nav-item ${currentView === 'compliance' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('compliance'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg>
                Override Reviews
              </a>
              <a className="nav-item" href="#" onClick={(e) => { e.preventDefault(); showToastMsg('Exporting compliance audit summary (PDF)...', 'success'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1z"/></svg>
                Export Reports
              </a>
            </>
          )}

          {currentUser?.role === 'System Admin' && (
            <>
              <a className={`nav-item ${currentView === 'dashboard' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('dashboard'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="1" width="6" height="6" rx="1.5"/><rect x="9" y="1" width="6" height="6" rx="1.5"/><rect x="1" y="9" width="6" height="6" rx="1.5"/><rect x="9" y="9" width="6" height="6" rx="1.5"/></svg>
                Global Analytics
              </a>
              <a className={`nav-item ${currentView === 'users' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('users'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="4" r="3" fill="none" stroke="currentColor" strokeWidth="1.5"/><path d="M14 14a6 6 0 0 0-12 0" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg>
                User Management
              </a>
              <a className={`nav-item ${currentView === 'dashboard' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('dashboard'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1l7 4v5c0 3.5-2.5 5.5-7 7-4.5-1.5-7-3.5-7-7V5L8 1z"/></svg>
                Fraud Trends
              </a>
              <a className={`nav-item ${currentView === 'settings' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('settings'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="3" fill="none" stroke="currentColor" strokeWidth="1.5"/><path d="M9.4 1a1.5 1.5 0 0 1 2.1 2.1m1.1.7a1.5 1.5 0 0 1 2.1 2.1" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg>
                System Settings
              </a>
              <a className={`nav-item ${currentView === 'dashboard' ? 'active' : ''}`} href="#" onClick={(e) => { e.preventDefault(); setCurrentView('dashboard'); }}>
                <svg className="nav-icon" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg>
                Platform Monitoring
              </a>
            </>
          )}
        </div>

        <div className="sidebar-bottom">
          <div className="user-card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div className="user-avatar" style={{ minWidth: '32px' }}>
                {currentUser?.username ? currentUser.username.split(' ').map(n => n[0]).join('') : 'U'}
              </div>
              <div className="user-info">
                <div className="user-name" style={{ fontSize: '13px', fontWeight: 600 }}>{currentUser?.username || 'User'}</div>
                <div className="user-role" style={{ fontSize: '11px', color: '#a1a1aa' }}>{currentUser?.role || 'Guest'}</div>
              </div>
            </div>
            <button 
              onClick={handleLogout} 
              style={{
                background: 'transparent',
                border: 'none',
                color: '#f43f5e',
                fontSize: '11px',
                cursor: 'pointer',
                fontWeight: 600,
                padding: '4px',
                marginLeft: '8px'
              }}
            >
              Exit
            </button>
          </div>
        </div>
      </aside>

      {/* MAIN AREA */}
      <main className="main">
        {/* TOPBAR */}
        <header className="topbar">
          <div className="topbar-title">
            SecureDocXAI Operations Center <span>/ {currentUser?.role}</span>
          </div>

          <div className="search-bar">
            <Search size={14} className="text-muted" />
            <input type="text" placeholder="Search applications, logs, audit keys..." />
          </div>

          <div className="topbar-actions">
            {currentUser?.role === 'Underwriting Officer' && (
              <>
                <button 
                  className="btn btn-primary flex items-center gap-2 mr-2"
                  onClick={() => setIsUploadModalOpen(true)}
                  style={{ padding: '6px 14px', fontSize: '13px' }}
                >
                  <Upload size={14} /> Upload Document
                </button>
                <button 
                  className="btn btn-ghost flex items-center gap-2 mr-2"
                  onClick={() => showToastMsg('Launching New Application Wizard...', 'info')}
                  style={{ padding: '6px 14px', fontSize: '13px', border: '1px solid #27272a' }}
                >
                  Create Application
                </button>
              </>
            )}



            {currentUser?.role === 'Branch Manager' && (
              <>
                <button 
                  className="btn btn-primary flex items-center gap-2 mr-2"
                  onClick={() => showToastMsg('Select pending case below to approve.', 'info')}
                  style={{ padding: '6px 14px', fontSize: '13px' }}
                >
                  Approve Application
                </button>
                <button 
                  className="btn btn-ghost flex items-center gap-2 mr-2"
                  onClick={() => showToastMsg('Override permissions verified. Select case in queue.', 'warning')}
                  style={{ padding: '6px 14px', fontSize: '13px', border: '1px solid #27272a' }}
                >
                  Override Decision
                </button>
              </>
            )}

            {currentUser?.role === 'Compliance Auditor' && (
              <button 
                className="btn btn-primary flex items-center gap-2 mr-2"
                onClick={() => showToastMsg('Exporting compliance registry (CSV)...', 'success')}
                style={{ padding: '6px 14px', fontSize: '13px' }}
              >
                Export Compliance Report
              </button>
            )}

            {currentUser?.role === 'System Admin' && (
              <>
                <button 
                  className="btn btn-primary flex items-center gap-2 mr-2"
                  onClick={() => setCurrentView('users')}
                  style={{ padding: '6px 14px', fontSize: '13px' }}
                >
                  Add User
                </button>
                <button 
                  className="btn btn-ghost flex items-center gap-2 mr-2"
                  onClick={() => setCurrentView('settings')}
                  style={{ padding: '6px 14px', fontSize: '13px', border: '1px solid #27272a' }}
                >
                  Configure Thresholds
                </button>
              </>
            )}
            <div className="status-pill">
              <div className="status-dot"></div> Live
            </div>
            <div className="icon-btn" onClick={refreshDashboard} title="Refresh">
              <RefreshCw size={14} />
            </div>
            <div className="icon-btn" title="Notifications" style={{ position: 'relative' }} onClick={() => setShowNotifications(!showNotifications)}>
              <Bell size={14} />
              {unreadCount > 0 && <div className="notif-dot"></div>}
              
              {showNotifications && (
                <div 
                  onClick={(e) => e.stopPropagation()} 
                  style={{
                    position: 'absolute',
                    top: '38px',
                    right: '0',
                    width: '320px',
                    maxHeight: '400px',
                    background: 'rgba(13, 17, 23, 0.95)',
                    backdropFilter: 'blur(16px)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '12px',
                    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.5)',
                    zIndex: 1000,
                    display: 'flex',
                    flexDirection: 'column',
                    cursor: 'default',
                    overflow: 'hidden'
                  }}
                >
                  {/* Dropdown Header */}
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '12px 16px',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
                    background: 'rgba(255, 255, 255, 0.02)'
                  }}>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: '#e4e4e7' }}>Notifications</span>
                    {unreadCount > 0 && (
                      <button 
                        onClick={handleMarkAllNotifsRead}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#3b82f6',
                          fontSize: '11px',
                          fontWeight: 500,
                          cursor: 'pointer',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          transition: 'background 0.2s'
                        }}
                        onMouseEnter={(e) => e.target.style.background = 'rgba(59, 130, 246, 0.1)'}
                        onMouseLeave={(e) => e.target.style.background = 'none'}
                      >
                        Mark all read
                      </button>
                    )}
                  </div>

                  {/* Dropdown Content */}
                  <div style={{
                    flex: 1,
                    overflowY: 'auto',
                    padding: '8px 0',
                    maxHeight: '300px'
                  }}>
                    {notifications.length === 0 ? (
                      <div style={{
                        padding: '32px 16px',
                        textAlign: 'center',
                        color: '#71717a',
                        fontSize: '12px'
                      }}>
                        No notifications
                      </div>
                    ) : (
                      notifications.map((notif) => (
                        <div 
                          key={notif.id}
                          style={{
                            padding: '12px 16px',
                            borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '4px',
                            background: notif.read ? 'transparent' : 'rgba(59, 130, 246, 0.03)',
                            transition: 'background 0.2s',
                            position: 'relative',
                            textAlign: 'left'
                          }}
                        >
                          <div style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'flex-start',
                            gap: '8px'
                          }}>
                            <span style={{ 
                              fontSize: '12px', 
                              fontWeight: notif.read ? 500 : 600, 
                              color: notif.read ? '#a1a1aa' : '#f4f4f5' 
                            }}>
                              {notif.document_name}
                            </span>
                            {!notif.read && (
                              <button 
                                onClick={(e) => handleMarkNotifRead(notif.id, e)}
                                style={{
                                  background: 'none',
                                  border: 'none',
                                  color: '#3b82f6',
                                  fontSize: '10px',
                                  fontWeight: 500,
                                  cursor: 'pointer',
                                  padding: '2px 4px',
                                  borderRadius: '3px'
                                }}
                                onMouseEnter={(e) => e.target.style.background = 'rgba(59, 130, 246, 0.1)'}
                                onMouseLeave={(e) => e.target.style.background = 'none'}
                              >
                                Mark read
                              </button>
                            )}
                          </div>
                          <span style={{ 
                            fontSize: '11px', 
                            color: notif.read ? '#71717a' : '#d4d4d8',
                            lineHeight: '1.4'
                          }}>
                            {notif.message}
                          </span>
                          <span style={{ 
                            fontSize: '9px', 
                            color: '#52525b',
                            marginTop: '2px'
                          }}>
                            {notif.created_at ? new Date(notif.created_at).toLocaleString() : ''}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* CONTENT AREA */}
        {currentView === 'dashboard' && (
        <div className="content">
          {/* STAT CARDS BASED ON ROLE */}
          <div className="stats-grid">
            {currentUser?.role === 'Underwriting Officer' && (
              <>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Documents Uploaded</div>
                    <div className="stat-icon" style={{ background: 'rgba(59,130,246,0.1)' }}><Upload size={14} color="#3b82f6"/></div>
                  </div>
                  <div className="stat-value" style={{ color: '#3b82f6' }}>{summaryData ? summaryData.total_documents : '...'}</div>
                  <div className="stat-sub">Personal upload count</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Pending Reviews</div>
                    <div className="stat-icon" style={{ background: 'rgba(245,158,11,0.1)' }}><svg width="15" height="15" viewBox="0 0 16 16" fill="var(--accent-amber)"><circle cx="8" cy="8" r="6" fill="none" stroke="var(--accent-amber)" strokeWidth="1.5"/><path d="M8 5v3l2.5 1.5" stroke="var(--accent-amber)" strokeWidth="1.5" fill="none" strokeLinecap="round"/></svg></div>
                  </div>
                  <div className="stat-value" style={{ color: 'var(--accent-amber)' }}>{summaryData ? summaryData.tier_breakdown?.review_queue : '...'}</div>
                  <div className="stat-sub">Awaiting decision approvals</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Applications Submitted</div>
                    <div className="stat-icon" style={{ background: 'rgba(16,185,129,0.1)' }}><CheckCircle size={14} color="#10b981"/></div>
                  </div>
                  <div className="stat-value" style={{ color: 'var(--accent-emerald)' }}>{summaryData ? (summaryData.total_documents - (summaryData.tier_breakdown?.review_queue || 0)) : '...'}</div>
                  <div className="stat-sub">Successfully processed</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Verification Status</div>
                    <div className="stat-icon" style={{ background: 'rgba(255,255,255,0.05)' }}><Check size={14} color="#fff"/></div>
                  </div>
                  <div className="stat-value" style={{ color: '#fff' }}>
                    {summaryData && summaryData.total_documents > 0 
                      ? `${Math.round(((summaryData.tier_breakdown?.verified + summaryData.tier_breakdown?.safe_to_process) / summaryData.total_documents) * 100)}%`
                      : '100%'}
                  </div>
                  <div className="stat-sub">Acceptance success index</div>
                </div>
              </>
            )}

            {currentUser?.role === 'Fraud Analyst' && (
              <>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Active Investigations</div>
                    <div className="stat-icon" style={{ background: 'rgba(245,158,11,0.1)' }}><Search size={14} color="#f59e0b"/></div>
                  </div>
                  <div className="stat-value" style={{ color: 'var(--accent-amber)' }}>{summaryData ? summaryData.tier_breakdown?.review_queue : '...'}</div>
                  <div className="stat-sub">Assigned alert tickets</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Escalated Cases</div>
                    <div className="stat-icon" style={{ background: 'rgba(249,115,22,0.1)' }}><AlertTriangle size={14} color="#f97316"/></div>
                  </div>
                  <div className="stat-value" style={{ color: '#f97316' }}>{summaryData ? summaryData.tier_breakdown?.review_queue : '...'}</div>
                  <div className="stat-sub">High severity anomalies</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Critical Alerts</div>
                    <div className="stat-icon" style={{ background: 'rgba(244,63,94,0.1)' }}><ShieldAlert size={14} color="#f43f5e"/></div>
                  </div>
                  <div className="stat-value" style={{ color: 'var(--risk-critical)' }}>{summaryData ? summaryData.tier_breakdown?.rejected : '...'}</div>
                  <div className="stat-sub">Tampering detections triggered</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">High Risk Documents</div>
                    <div className="stat-icon" style={{ background: 'rgba(255,255,255,0.05)' }}><Shield size={14} color="#fff"/></div>
                  </div>
                  <div className="stat-value" style={{ color: '#fff' }}>{summaryData ? summaryData.tier_breakdown?.rejected : '...'}</div>
                  <div className="stat-sub">Blocked pipeline runs</div>
                </div>
              </>
            )}

            {currentUser?.role === 'Branch Manager' && (
              <>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Approval Queue</div>
                    <div className="stat-icon" style={{ background: 'rgba(245,158,11,0.1)' }}><Search size={14} color="#f59e0b"/></div>
                  </div>
                  <div className="stat-value" style={{ color: 'var(--accent-amber)' }}>{summaryData ? summaryData.tier_breakdown?.review_queue : '...'}</div>
                  <div className="stat-sub">Needs branch manager review</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Rejected Applications</div>
                    <div className="stat-icon" style={{ background: 'rgba(244,63,94,0.1)' }}><ShieldAlert size={14} color="#f43f5e"/></div>
                  </div>
                  <div className="stat-value" style={{ color: 'var(--risk-critical)' }}>{summaryData ? summaryData.tier_breakdown?.rejected : '...'}</div>
                  <div className="stat-sub">Fraud blocks at branch level</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Branch Fraud Rate</div>
                    <div className="stat-icon" style={{ background: 'rgba(249,115,22,0.1)' }}><AlertTriangle size={14} color="#f97316"/></div>
                  </div>
                  <div className="stat-value" style={{ color: '#f97316' }}>{summaryData ? `${summaryData.fraud_rate_percent}%` : '...'}</div>
                  <div className="stat-sub">Calculated risk metrics</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Analyst Workload</div>
                    <div className="stat-icon" style={{ background: 'rgba(59,130,246,0.1)' }}><Check size={14} color="#3b82f6"/></div>
                  </div>
                  <div className="stat-value" style={{ color: '#fff' }}>Optimal</div>
                  <div className="stat-sub">Capacity is within threshold limits</div>
                </div>
              </>
            )}

            {currentUser?.role === 'Compliance Auditor' && (
              <>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Compliance Violations</div>
                    <div className="stat-icon" style={{ background: 'rgba(244,63,94,0.1)' }}><ShieldAlert size={14} color="#f43f5e"/></div>
                  </div>
                  <div className="stat-value" style={{ color: 'var(--risk-critical)' }}>0</div>
                  <div className="stat-sub">No regulations breached</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Override Events</div>
                    <div className="stat-icon" style={{ background: 'rgba(249,115,22,0.1)' }}><AlertTriangle size={14} color="#f97316"/></div>
                  </div>
                  <div className="stat-value" style={{ color: '#f97316' }}>{summaryData ? summaryData.tier_breakdown?.review_queue : '0'}</div>
                  <div className="stat-sub">Logged manual override decisions</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Audit Timeline</div>
                    <div className="stat-icon" style={{ background: 'rgba(59,130,246,0.1)' }}><Clock size={14} color="#3b82f6"/></div>
                  </div>
                  <div className="stat-value" style={{ color: '#3b82f6' }}>{summaryData ? summaryData.total_documents : '0'}</div>
                  <div className="stat-sub">Indexed security events</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Export Reports</div>
                    <div className="stat-icon" style={{ background: 'rgba(16,185,129,0.1)' }}><CheckCircle size={14} color="#10b981"/></div>
                  </div>
                  <div className="stat-value" style={{ color: 'var(--accent-emerald)' }}>Active</div>
                  <div className="stat-sub">Regulatory templates available</div>
                </div>
              </>
            )}

            {currentUser?.role === 'System Admin' && (
              <>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">System Users</div>
                    <div className="stat-icon" style={{ background: 'rgba(59,130,246,0.1)' }}><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="4" r="3"/><path d="M14 14a6 6 0 0 0-12 0"/></svg></div>
                  </div>
                  <div className="stat-value" style={{ color: '#3b82f6' }}>12</div>
                  <div className="stat-sub">Active login profiles</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Fraud Trends</div>
                    <div className="stat-icon" style={{ background: 'rgba(244,63,94,0.1)' }}><ShieldAlert size={14} color="#f43f5e"/></div>
                  </div>
                  <div className="stat-value" style={{ color: 'var(--risk-critical)' }}>{summaryData ? `${summaryData.fraud_rate_percent}%` : '...'}</div>
                  <div className="stat-sub">Avg global fraud rate</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Branch Activity</div>
                    <div className="stat-icon" style={{ background: 'rgba(249,115,22,0.1)' }}><AlertTriangle size={14} color="#f97316"/></div>
                  </div>
                  <div className="stat-value" style={{ color: '#f97316' }}>5 Active</div>
                  <div className="stat-sub">Cross-branch monitoring</div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <div className="stat-label">Platform Health</div>
                    <div className="stat-icon" style={{ background: 'rgba(16,185,129,0.1)' }}><CheckCircle size={14} color="#10b981"/></div>
                  </div>
                  <div className="stat-value" style={{ color: 'var(--accent-emerald)' }}>99.98%</div>
                  <div className="stat-sub">API servers online</div>
                </div>
              </>
            )}
          </div>

          {/* MAIN GRID */}
          <div className="main-grid" style={{ marginBottom: '24px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Trend Chart */}
              <div className="card">
                <div className="card-inner">
                  <div className="section-header">
                    <div>
                      <div className="section-title">Global Fraud Detection Trends</div>
                      <div className="section-sub">Daily case volume — last 30 days</div>
                    </div>
                  </div>
                  <div className="chart-area">
                    <ResponsiveContainer width="100%" height={200}>
                      <AreaChart data={trendsData || []} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
                        <defs>
                          <linearGradient id="colorScanned" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                          </linearGradient>
                          <linearGradient id="colorFraud" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.3}/>
                            <stop offset="95%" stopColor="#f43f5e" stopOpacity={0}/>
                          </linearGradient>
                        </defs>
                        <XAxis dataKey="date" stroke="#52525b" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(val) => new Date(val).toLocaleDateString([], { month: 'short', day: 'numeric' })} />
                        <YAxis stroke="#52525b" fontSize={12} tickLine={false} axisLine={false} />
                        <Tooltip content={<CustomTooltip />} />
                        <Area type="monotone" dataKey="total_scanned" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#colorScanned)" />
                        <Area type="monotone" dataKey="high_risk" stroke="#f43f5e" strokeWidth={2} fillOpacity={1} fill="url(#colorFraud)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              {currentUser?.role === 'System Admin' && (
                <div className="card" style={{ padding: '24px' }}>
                  <div className="section-title" style={{ marginBottom: '16px' }}>Enterprise Command Center Metrics</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                    <div style={{ background: '#09090b', padding: '16px', borderRadius: '12px', border: '1px solid #27272a' }}>
                      <div style={{ color: '#a1a1aa', fontSize: '12px' }}>OCR HEALTH RATIO</div>
                      <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#10b981', marginTop: '4px' }}>98.4%</div>
                    </div>
                    <div style={{ background: '#09090b', padding: '16px', borderRadius: '12px', border: '1px solid #27272a' }}>
                      <div style={{ color: '#a1a1aa', fontSize: '12px' }}>AVG SCAN RESPONSE TIME</div>
                      <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#fff', marginTop: '4px' }}>0.82s</div>
                    </div>
                    <div style={{ background: '#09090b', padding: '16px', borderRadius: '12px', border: '1px solid #27272a' }}>
                      <div style={{ color: '#a1a1aa', fontSize: '12px' }}>SYSTEM UPTIME</div>
                      <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#3b82f6', marginTop: '4px' }}>34d 12h 05m</div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Activity Feed */}
            <div className="card activity-card">
              <div className="activity-header">
                <div className="section-header">
                  <div>
                    <div className="section-title">Live Activity Timeline</div>
                    <div className="section-sub">Real-time pipeline operations</div>
                  </div>
                  <div className="status-pill" style={{ fontSize: '11px', padding: '3px 8px' }}>
                    <div className="status-dot"></div> Live
                  </div>
                </div>
              </div>
              <div className="activity-list">
                {activityData ? activityData.map((item, idx) => {
                  const badgeCol = item.risk_tier === 'high' ? '#f97316' : item.risk_tier === 'critical' ? '#f43f5e' : item.risk_tier === 'medium' ? '#f59e0b' : '#10b981';
                  const badgeBg = `rgba(${badgeCol === '#f43f5e' ? '244,63,94' : badgeCol === '#f97316' ? '249,115,22' : badgeCol === '#f59e0b' ? '245,158,11' : '16,185,129'}, 0.12)`;
                  return (
                    <div className="activity-item" key={item.analysis_id || idx} style={{ animationDelay: `${idx * 80}ms` }}>
                      <div className="activity-dot" style={{ color: badgeCol, background: badgeCol }}></div>
                      <div className="activity-content">
                        <div className="activity-text text-secondary" style={{ fontSize: '12.5px', lineHeight: '1.4' }}>
                          <span style={{ color: '#fff', fontWeight: 600 }}>{item.uploaded_by || 'Underwriter'}</span> — <em>{item.branch || 'Global Branch'}</em><br />
                          Processed <strong>{item.document_name || 'Doc'}</strong> (Score: {Math.round(item.risk_score)}/100)
                        </div>
                        <div className="activity-time">{new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
                      </div>
                      <div className="activity-badge" style={{ background: badgeBg, color: badgeCol }}>{item.risk_tier.toUpperCase()}</div>
                    </div>
                  )
                }) : <div className="text-secondary p-4">Loading activities...</div>}
              </div>
            </div>
          </div>
        </div>
        )}

        {/* USER MANAGEMENT VIEW FOR SYSTEM ADMIN */}
        {currentView === 'users' && (
          <div className="content" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div className="section-header">
              <div>
                <div className="section-title">User Management Dashboard</div>
                <div className="section-sub">Configure user profile roles and branch privileges.</div>
              </div>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '24px' }}>
              <div className="card" style={{ padding: '24px' }}>
                <div className="section-title" style={{ marginBottom: '16px', fontSize: '15px' }}>Registered Operators</div>
                <table style={{ width: '100%', borderCollapse: 'collapse', color: '#fff', textAlign: 'left', fontSize: '13px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #27272a', color: '#a1a1aa' }}>
                      <th style={{ padding: '12px 8px' }}>NAME</th>
                      <th style={{ padding: '12px 8px' }}>EMAIL</th>
                      <th style={{ padding: '12px 8px' }}>ROLE</th>
                      <th style={{ padding: '12px 8px' }}>BRANCH</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr style={{ borderBottom: '1px solid #27272a' }}>
                      <td style={{ padding: '12px 8px' }}>Underwriting Officer</td>
                      <td style={{ padding: '12px 8px' }}>underwriter@bank.com</td>
                      <td style={{ padding: '12px 8px', color: '#10b981', fontWeight: 600 }}>Underwriting Officer</td>
                      <td style={{ padding: '12px 8px' }}>Canara Bank</td>
                    </tr>
                    <tr style={{ borderBottom: '1px solid #27272a' }}>
                      <td style={{ padding: '12px 8px' }}>Fraud Analyst</td>
                      <td style={{ padding: '12px 8px' }}>analyst@bank.com</td>
                      <td style={{ padding: '12px 8px', color: '#3b82f6', fontWeight: 600 }}>Fraud Analyst</td>
                      <td style={{ padding: '12px 8px' }}>Canara Bank</td>
                    </tr>
                    <tr style={{ borderBottom: '1px solid #27272a' }}>
                      <td style={{ padding: '12px 8px' }}>Branch Manager</td>
                      <td style={{ padding: '12px 8px' }}>manager@bank.com</td>
                      <td style={{ padding: '12px 8px', color: '#f59e0b', fontWeight: 600 }}>Branch Manager</td>
                      <td style={{ padding: '12px 8px' }}>Canara Bank</td>
                    </tr>
                    <tr style={{ borderBottom: '1px solid #27272a' }}>
                      <td style={{ padding: '12px 8px' }}>Compliance Auditor</td>
                      <td style={{ padding: '12px 8px' }}>auditor@bank.com</td>
                      <td style={{ padding: '12px 8px', color: '#8b5cf6', fontWeight: 600 }}>Compliance Auditor</td>
                      <td style={{ padding: '12px 8px' }}>Canara Bank</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              
              <div className="card" style={{ padding: '24px' }}>
                <div className="section-title" style={{ marginBottom: '16px', fontSize: '15px' }}>Provision New User</div>
                <form onSubmit={(e) => { e.preventDefault(); showToastMsg('User successfully provisioned!', 'success'); }} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <input type="text" placeholder="Username" required style={{ background: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '10px', color: '#fff', fontSize: '13px' }} />
                  <input type="email" placeholder="Email Address" required style={{ background: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '10px', color: '#fff', fontSize: '13px' }} />
                  <input type="password" placeholder="Temporary Password" required style={{ background: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '10px', color: '#fff', fontSize: '13px' }} />
                  <select required style={{ background: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '10px', color: '#fff', fontSize: '13px' }}>
                    <option value="Underwriting Officer">Underwriting Officer</option>
                    <option value="Fraud Analyst">Fraud Analyst</option>
                    <option value="Branch Manager">Branch Manager</option>
                    <option value="Compliance Auditor">Compliance Auditor</option>
                  </select>
                  <button type="submit" className="btn btn-primary" style={{ padding: '10px', fontSize: '13px' }}>Create Account</button>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* SYSTEM SETTINGS VIEW */}
        {currentView === 'settings' && (
          <div className="content" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div className="section-header">
              <div>
                <div className="section-title">System Settings & Threshold Policies</div>
                <div className="section-sub">Configure platform scanning parameters and compliance limits.</div>
              </div>
            </div>
            <div className="card" style={{ padding: '24px', maxWidth: '600px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#fff', marginBottom: '8px' }}>CRITICAL FRAUD SCORING THRESHOLD</label>
                  <input type="range" min="50" max="95" defaultValue="70" style={{ width: '100%' }} />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#a1a1aa', marginTop: '4px' }}>
                    <span>50%</span>
                    <span>70% (Default)</span>
                    <span>95%</span>
                  </div>
                </div>

                <div style={{ borderBottom: '1px solid #27272a', margin: '8px 0' }}></div>

                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#fff', marginBottom: '8px' }}>SLA NOTIFICATION POLICY</label>
                  <select style={{ background: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '10px', color: '#fff', fontSize: '13px', width: '100%' }}>
                    <option>SLA Alert 30m prior to expiration</option>
                    <option>SLA Alert 60m prior to expiration</option>
                    <option>Mute SLA Warnings</option>
                  </select>
                </div>
                
                <button className="btn btn-primary" onClick={() => showToastMsg('Policies successfully updated!', 'success')} style={{ alignSelf: 'flex-start', padding: '10px 20px', fontSize: '13px' }}>
                  Save Policy Configuration
                </button>
              </div>
            </div>
          </div>
        )}

        {currentView === 'queue' && (
          <ReviewQueue 
            currentUser={currentUser}
            onViewDocument={(analysisId, docId) => {
              setSelectedAnalysisId(analysisId);
              setSelectedDocumentId(docId);
              setCurrentView('insights');
            }}
          />
        )}
        
        {currentView === 'insights' && (
          <DocumentInsights 
            analysisId={selectedAnalysisId}
            documentId={selectedDocumentId}
            currentUser={currentUser}
            onBack={() => {
              // Invalidate queue so it refreshes after returning from a decision
              queryClient.invalidateQueries({ queryKey: ['dashboard'] });
              setCurrentView('queue');
            }}
            onDecisionSuccess={() => {
              // After a decision, invalidate queue data so it reflects new status
              queryClient.invalidateQueries({ queryKey: ['dashboard'] });
            }}
          />
        )}

        {currentView === 'compliance' && (
          <ComplianceLogs />
        )}

      </main>

      {/* Upload Modal */}
      <UploadModal 
        isOpen={isUploadModalOpen} 
        onClose={() => setIsUploadModalOpen(false)} 
        onUploadComplete={handleUploadComplete} 
      />

      {/* Toast Notification */}
      <div id="toast" style={{
        position: 'fixed', bottom: '24px', left: '50%', transform: toast.visible ? 'translateX(-50%) translateY(0)' : 'translateX(-50%) translateY(60px)',
        background: 'var(--bg-elevated)', border: '1px solid var(--border-hover)',
        borderRadius: 'var(--radius-sm)', padding: '10px 20px', fontSize: '13px', fontWeight: '500',
        zIndex: 9999, opacity: toast.visible ? 1 : 0, transition: 'all 0.3s cubic-bezier(0.4,0,0.2,1)',
        display: 'flex', alignItems: 'center', gap: '8px', whiteSpace: 'nowrap', color: 'var(--text-primary)'
      }}>
        {toast.message}
      </div>
    </div>
  );
};

const RiskFactor = ({ name, val, color }) => (
  <div className="risk-factor">
    <div className="risk-factor-header">
      <span className="risk-factor-name">{name}</span>
      <span className="risk-factor-val" style={{ color }}>{val}%</span>
    </div>
    <div className="risk-bar-track">
      <div className="risk-bar-fill" style={{ width: `${val}%`, background: color }}></div>
    </div>
  </div>
);

const WorkflowStep = ({ num, name, desc, state }) => {
  const stateClass = state === 'done' ? 'wf-complete' : state === 'running' ? 'wf-active' : 'wf-pending';
  const icon = state === 'done' ? '✓' : state === 'running' ? '⟳' : num;
  return (
    <div className="wf-step">
      <div className={`wf-num ${stateClass}`}>{icon}</div>
      <div className="wf-info">
        <div className="wf-name">{name}</div>
        <div className="wf-desc">{desc}</div>
      </div>
      <div className={`wf-status ${state}`}>{state === 'done' ? 'Done' : state === 'running' ? 'Running' : 'Pending'}</div>
    </div>
  );
};

export default App;
