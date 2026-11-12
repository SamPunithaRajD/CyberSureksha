import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Shield, RefreshCw, Filter, Calendar, User } from 'lucide-react';

const ComplianceLogs = () => {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [actionFilter, setActionFilter] = useState('');
  const [error, setError] = useState('');

  const fetchLogs = async () => {
    setIsLoading(true);
    setError('');
    try {
      const url = actionFilter 
        ? `http://localhost:8000/api/v1/compliance/logs?action=${actionFilter}`
        : 'http://localhost:8000/api/v1/compliance/logs';
      const response = await axios.get(url);
      setLogs(response.data.logs || []);
      setTotal(response.data.total || 0);
    } catch (err) {
      console.error(err);
      setError('Failed to fetch system audit logs. Verify your role permissions.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [actionFilter]);

  const uniqueActions = [
    { value: '', label: 'All Actions' },
    { value: 'user_login', label: 'User Login' },
    { value: 'document_upload', label: 'Document Upload' },
    { value: 'document_delete', label: 'Document Delete' },
    { value: 'analysis_trigger', label: 'Analysis Trigger' },
    { value: 'underwriter_decision', label: 'Underwriter Decision' },
  ];

  return (
    <div className="content" style={{ animation: 'fadeIn 0.4s ease-out' }}>
      <div className="section-header" style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 600, color: '#fff', margin: 0 }}>System Compliance Audit Trails</h2>
          <p style={{ fontSize: '13px', color: '#a1a1aa', margin: '4px 0 0' }}>Immutable blockchain-like internal system transaction log</p>
        </div>
        <button 
          onClick={fetchLogs} 
          disabled={isLoading}
          className="btn btn-secondary flex items-center gap-2"
          style={{ padding: '6px 12px', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} /> Refresh Logs
        </button>
      </div>

      {error && (
        <div style={{
          background: 'rgba(244, 63, 94, 0.1)',
          border: '1px solid rgba(244, 63, 94, 0.2)',
          color: '#f43f5e',
          padding: '12px 16px',
          borderRadius: '12px',
          fontSize: '13px',
          marginBottom: '20px'
        }}>
          ⚠️ {error}
        </div>
      )}

      {/* Filter Bar */}
      <div style={{
        background: 'rgba(255, 255, 255, 0.02)',
        border: '1px solid rgba(255, 255, 255, 0.06)',
        borderRadius: '12px',
        padding: '12px 20px',
        marginBottom: '20px',
        display: 'flex',
        alignItems: 'center',
        gap: '12px'
      }}>
        <Filter size={16} style={{ color: '#52525b' }} />
        <span style={{ fontSize: '13px', fontWeight: 500, color: '#a1a1aa' }}>Filter by Action:</span>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {uniqueActions.map(act => (
            <button
              key={act.value}
              onClick={() => setActionFilter(act.value)}
              style={{
                padding: '6px 12px',
                borderRadius: '8px',
                fontSize: '12px',
                fontWeight: 500,
                border: '1px solid',
                borderColor: actionFilter === act.value ? '#3b82f6' : 'rgba(255, 255, 255, 0.08)',
                background: actionFilter === act.value ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
                color: actionFilter === act.value ? '#3b82f6' : '#a1a1aa',
                cursor: 'pointer',
                transition: 'all 0.2s'
              }}
            >
              {act.label}
            </button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', fontSize: '13px', color: '#52525b' }}>
          Total logs: <strong style={{ color: '#e4e4e7' }}>{total}</strong>
        </div>
      </div>

      {/* Logs Table */}
      <div style={{
        background: 'rgba(18, 18, 21, 0.4)',
        backdropFilter: 'blur(20px)',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '16px',
        overflow: 'hidden'
      }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', background: 'rgba(255, 255, 255, 0.02)' }}>
                <th style={{ padding: '16px 20px', fontSize: '12px', fontWeight: 600, color: '#52525b', textTransform: 'uppercase' }}>Timestamp</th>
                <th style={{ padding: '16px 20px', fontSize: '12px', fontWeight: 600, color: '#52525b', textTransform: 'uppercase' }}>User / Role</th>
                <th style={{ padding: '16px 20px', fontSize: '12px', fontWeight: 600, color: '#52525b', textTransform: 'uppercase' }}>Action</th>
                <th style={{ padding: '16px 20px', fontSize: '12px', fontWeight: 600, color: '#52525b', textTransform: 'uppercase' }}>Details / Metadata</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan="4" style={{ padding: '40px', textAlign: 'center', color: '#a1a1aa' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                      <RefreshCw className="animate-spin" size={16} /> Loading audit trail...
                    </div>
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan="4" style={{ padding: '40px', textAlign: 'center', color: '#a1a1aa' }}>
                    No audit logs matching selection
                  </td>
                </tr>
              ) : (
                logs.map((log, idx) => (
                  <tr key={log.id || idx} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)', transition: 'background 0.2s' }}>
                    <td style={{ padding: '16px 20px', fontSize: '13px', color: '#a1a1aa', whiteSpace: 'nowrap' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Calendar size={13} style={{ color: '#52525b' }} />
                        {new Date(log.timestamp).toLocaleString()}
                      </div>
                    </td>
                    <td style={{ padding: '16px 20px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{
                          width: '24px',
                          height: '24px',
                          borderRadius: '50%',
                          background: 'rgba(255,255,255,0.06)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '11px',
                          fontWeight: 600,
                          color: '#e4e4e7'
                        }}>
                          {log.username ? log.username[0].toUpperCase() : 'U'}
                        </div>
                        <div>
                          <div style={{ fontSize: '13px', fontWeight: 500, color: '#e4e4e7' }}>{log.username || 'System'}</div>
                          <div style={{ fontSize: '11px', color: '#52525b' }}>{log.role || 'System Service'}</div>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: '16px 20px' }}>
                      <span style={{
                        padding: '4px 8px',
                        borderRadius: '6px',
                        fontSize: '11px',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        background: log.action?.includes('delete') || log.action?.includes('reject') ? 'rgba(244, 63, 94, 0.1)' : 'rgba(59, 130, 246, 0.1)',
                        color: log.action?.includes('delete') || log.action?.includes('reject') ? '#f43f5e' : '#3b82f6',
                      }}>
                        {log.action?.replace('_', ' ')}
                      </span>
                    </td>
                    <td style={{ padding: '16px 20px', fontSize: '13px', color: '#d4d4d8' }}>
                      <pre style={{ margin: 0, fontFamily: 'monospace', fontSize: '11px', whiteSpace: 'pre-wrap', color: '#a1a1aa' }}>
                        {JSON.stringify(log.details, null, 2)}
                      </pre>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default ComplianceLogs;
