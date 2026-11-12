import React, { useState } from 'react';
import axios from 'axios';
import { Shield, Key, Mail, Loader2 } from 'lucide-react';

const Login = ({ onLoginSuccess }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async (e) => {
    if (e) e.preventDefault();
    if (!email || !password) {
      setError('Please fill in all fields');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const response = await axios.post('http://localhost:8000/api/v1/auth/login', {
        email,
        password,
      });

      const { access_token, user } = response.data;
      localStorage.setItem('token', access_token);
      localStorage.setItem('user', JSON.stringify(user));
      
      // Clear legacy/stale caches on fresh login
      localStorage.removeItem('selectedIssueIndex');
      
      // Configure default axios authorization header
      axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
      
      onLoginSuccess(access_token, user);
    } catch (err) {
      console.error(err);
      setError(
        err.response?.data?.detail || 
        'Login failed. Please check your credentials and try again.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  // Demo shortcut login handler for Hackathon judging
  const handleQuickLogin = (roleEmail) => {
    setEmail(roleEmail);
    setPassword('Password123');
    // We execute login in the next tick to allow state update to apply
    setTimeout(() => {
      const form = document.getElementById('login-form');
      if (form) {
        const fakeEvent = { preventDefault: () => {} };
        // Directly invoke handleLogin with current credentials
        setIsLoading(true);
        axios.post('http://localhost:8000/api/v1/auth/login', {
          email: roleEmail,
          password: 'Password123',
        }).then(response => {
          const { access_token, user } = response.data;
          localStorage.setItem('token', access_token);
          localStorage.setItem('user', JSON.stringify(user));
          localStorage.removeItem('selectedIssueIndex');
          axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
          onLoginSuccess(access_token, user);
        }).catch(err => {
          setError('Demo login failed: ' + (err.response?.data?.detail || err.message));
        }).finally(() => {
          setIsLoading(false);
        });
      }
    }, 100);
  };

  const demoAccounts = [
    { label: 'Underwriter', email: 'underwriter@bank.com', color: '#10b981' },
    { label: 'Analyst', email: 'analyst@bank.com', color: '#3b82f6' },
    { label: 'Manager', email: 'manager@bank.com', color: '#f59e0b' },
    { label: 'Auditor', email: 'auditor@bank.com', color: '#8b5cf6' },
    { label: 'Admin', email: 'admin@bank.com', color: '#ef4444' },
  ];

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      width: '100vw',
      background: '#09090b',
      position: 'relative',
      overflow: 'hidden',
      fontFamily: 'system-ui, -apple-system, sans-serif'
    }}>
      {/* Background orbs */}
      <div className="bg-orbs" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 0 }}>
        <div className="orb orb-1" style={{ top: '-10%', left: '10%' }}></div>
        <div className="orb orb-2" style={{ bottom: '-10%', right: '10%' }}></div>
      </div>

      <div style={{
        width: '100%',
        maxWidth: '440px',
        padding: '40px',
        background: 'rgba(18, 18, 21, 0.6)',
        backdropFilter: 'blur(20px)',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '24px',
        boxShadow: '0 20px 40px rgba(0, 0, 0, 0.4)',
        zIndex: 1,
        textAlign: 'center',
        boxSizing: 'border-box'
      }}>
        {/* Logo Header */}
        <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '48px', height: '48px', borderRadius: '12px', background: 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.2)', marginBottom: '16px', color: '#3b82f6' }}>
          <Shield size={24} />
        </div>
        
        <h2 style={{ fontSize: '24px', fontWeight: 600, color: '#fff', margin: '0 0 8px 0', letterSpacing: '-0.5px' }}>
          SecureDocX<span style={{ color: '#3b82f6' }}>AI</span>
        </h2>
        <p style={{ fontSize: '14px', color: '#a1a1aa', margin: '0 0 32px 0' }}>
          Enterprise Underwriting & Fraud Intelligence Portal
        </p>

        {error && (
          <div style={{
            background: 'rgba(244, 63, 94, 0.1)',
            border: '1px solid rgba(244, 63, 94, 0.2)',
            color: '#f43f5e',
            padding: '12px 16px',
            borderRadius: '12px',
            fontSize: '13px',
            textAlign: 'left',
            marginBottom: '24px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            <span>⚠️</span> {error}
          </div>
        )}

        <form id="login-form" onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Email field */}
          <div style={{ display: 'flex', flexDirection: 'column', textAlign: 'left', gap: '6px' }}>
            <label style={{ fontSize: '12px', fontWeight: 500, color: '#a1a1aa' }}>EMAIL ADDRESS</label>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <Mail size={16} style={{ position: 'absolute', left: '16px', color: '#52525b' }} />
              <input
                type="email"
                placeholder="name@bank.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={{
                  width: '100%',
                  padding: '14px 16px 14px 44px',
                  background: '#09090b',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '12px',
                  color: '#fff',
                  fontSize: '14px',
                  outline: 'none',
                  transition: 'border-color 0.2s',
                  boxSizing: 'border-box'
                }}
                onFocus={(e) => e.target.style.borderColor = '#3b82f6'}
                onBlur={(e) => e.target.style.borderColor = 'rgba(255, 255, 255, 0.08)'}
                required
              />
            </div>
          </div>

          {/* Password field */}
          <div style={{ display: 'flex', flexDirection: 'column', textAlign: 'left', gap: '6px' }}>
            <label style={{ fontSize: '12px', fontWeight: 500, color: '#a1a1aa' }}>PASSWORD</label>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <Key size={16} style={{ position: 'absolute', left: '16px', color: '#52525b' }} />
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{
                  width: '100%',
                  padding: '14px 16px 14px 44px',
                  background: '#09090b',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '12px',
                  color: '#fff',
                  fontSize: '14px',
                  outline: 'none',
                  transition: 'border-color 0.2s',
                  boxSizing: 'border-box'
                }}
                onFocus={(e) => e.target.style.borderColor = '#3b82f6'}
                onBlur={(e) => e.target.style.borderColor = 'rgba(255, 255, 255, 0.08)'}
                required
              />
            </div>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isLoading}
            style={{
              width: '100%',
              padding: '14px',
              background: '#3b82f6',
              color: '#fff',
              border: 'none',
              borderRadius: '12px',
              fontSize: '14px',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              transition: 'background 0.2s, opacity 0.2s',
              marginTop: '12px'
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = '#2563eb'}
            onMouseLeave={(e) => e.currentTarget.style.background = '#3b82f6'}
          >
            {isLoading ? (
              <>
                <Loader2 size={16} className="animate-spin" /> Verifying Credentials...
              </>
            ) : (
              'Sign In to Dashboard'
            )}
          </button>
        </form>

        {/* Divider */}
        <div style={{ display: 'flex', alignItems: 'center', margin: '24px 0', gap: '16px' }}>
          <div style={{ flex: 1, height: '1px', background: 'rgba(255, 255, 255, 0.08)' }}></div>
          <span style={{ fontSize: '11px', fontWeight: 600, color: '#52525b', letterSpacing: '1px' }}>DEMO QUICK ACCESS</span>
          <div style={{ flex: 1, height: '1px', background: 'rgba(255, 255, 255, 0.08)' }}></div>
        </div>

        {/* Quick Access Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
          {demoAccounts.map((acc) => (
            <button
              key={acc.label}
              onClick={() => handleQuickLogin(acc.email)}
              disabled={isLoading}
              style={{
                padding: '8px 4px',
                background: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid rgba(255, 255, 255, 0.06)',
                borderRadius: '8px',
                color: '#fff',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.2s',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '4px'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
                e.currentTarget.style.borderColor = acc.color;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.02)';
                e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.06)';
              }}
            >
              <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: acc.color }}></div>
              {acc.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default Login;
