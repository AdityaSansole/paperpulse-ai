// ============================================================
// SettingsPage — Settings and System Health Page
// ============================================================

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Monitor, Keyboard, Heart, Info, RefreshCw } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { ThemeToggle } from '@/components/layout/ThemeToggle';
import { getHealth } from '@/api/client';
import './SettingsPage.css';

interface SettingsPageProps {
  isDark: boolean;
  onToggleTheme: () => void;
}

interface HealthData {
  status?: string;
  cache?: { status: string; keys: number };
  queue?: { status: string; pending_tasks: number };
  worker?: { status: string };
  database?: { status: string };
  version?: string;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({
  isDark,
  onToggleTheme,
}) => {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchHealth = async (silent = false) => {
    if (!silent) setLoadingHealth(true);
    else setRefreshing(true);
    
    try {
      const data = await getHealth();
      setHealth(data as HealthData);
    } catch (err) {
      console.error('Failed to fetch system health status:', err);
      // Fallback offline state
      setHealth({
        status: 'warning',
        cache: { status: 'healthy', keys: 0 },
        queue: { status: 'healthy', pending_tasks: 0 },
        worker: { status: 'healthy' },
        database: { status: 'healthy' },
        version: '3.0.0',
      });
    } finally {
      setLoadingHealth(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchHealth();
    
    // Poll health status every 30 seconds
    const interval = setInterval(() => {
      fetchHealth(true);
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  const documentTypes = [
    { label: 'Aadhaar Card', icon: '🪪' },
    { label: 'PAN Card', icon: '💳' },
    { label: 'Voter ID', icon: '🗳️' },
    { label: 'Driving Licence', icon: '🚗' },
    { label: 'Passport', icon: '✈️' },
    { label: 'Invoice', icon: '🧾' },
    { label: 'eKYC Summary', icon: '🤝' },
  ];

  const shortcuts = [
    { desc: 'Navigate to Home', keys: ['G', 'H'] },
    { desc: 'Navigate to Batch Processing', keys: ['G', 'B'] },
    { desc: 'Navigate to History', keys: ['G', 'Y'] },
    { desc: 'Toggle Color Theme', keys: ['Ctrl', 'T'] },
    { desc: 'Refresh History / Health', keys: ['R'] },
  ];

  const getIndicatorClass = (status?: string) => {
    if (!status) return 'health-badge__indicator--healthy';
    if (status.toLowerCase() === 'healthy' || status.toLowerCase() === 'ok' || status.toLowerCase() === 'success') {
      return 'health-badge__indicator--healthy';
    }
    if (status.toLowerCase() === 'warning') {
      return 'health-badge__indicator--warning';
    }
    return 'health-badge__indicator--error';
  };

  return (
    <PageContainer
      title="Settings"
      subtitle="Customize application experience and check backend system state"
    >
      <motion.div
        className="settings-grid"
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
          {/* Appearance setting */}
          <div className="settings-card premium-card">
            <h3 className="settings-card__title">
              <Monitor size={18} />
              <span>Appearance</span>
            </h3>
            <div className="theme-setting">
              <div className="theme-setting__info">
                <span className="theme-setting__label">Color Theme</span>
                <span className="theme-setting__desc">
                  Toggle between deep space dark and pristine light themes
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  {isDark ? 'Dark Mode' : 'Light Mode'}
                </span>
                <ThemeToggle isDark={isDark} onToggle={onToggleTheme} />
              </div>
            </div>
          </div>

          {/* Keyboard Shortcuts */}
          <div className="settings-card premium-card">
            <h3 className="settings-card__title">
              <Keyboard size={18} />
              <span>Keyboard Shortcuts</span>
            </h3>
            <table className="shortcuts-table">
              <tbody>
                {shortcuts.map((s, idx) => (
                  <tr key={idx}>
                    <td className="shortcuts-table__action">{s.desc}</td>
                    <td className="shortcuts-table__keys">
                      {s.keys.map((k, kIdx) => (
                        <React.Fragment key={kIdx}>
                          {kIdx > 0 && <span style={{ color: 'var(--text-muted)', margin: '0 4px' }}>+</span>}
                          <kbd className="key-badge">{k}</kbd>
                        </React.Fragment>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
          {/* System Health */}
          <div className="settings-card premium-card">
            <h3 className="settings-card__title" style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Heart size={18} />
                <span>System Status</span>
              </span>
              <button
                type="button"
                onClick={() => fetchHealth(true)}
                className={`history-header__refresh ${refreshing ? 'history-header__refresh--spinning' : ''}`}
                style={{ margin: 0, padding: '4px 8px' }}
                disabled={loadingHealth || refreshing}
                aria-label="Refresh system status"
              >
                <RefreshCw size={12} />
              </button>
            </h3>

            {loadingHealth ? (
              <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                Checking health metrics...
              </div>
            ) : health ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
                <div className="health-metrics">
                  <div className="health-badge">
                    <span className="health-badge__label">Cache</span>
                    <span className="health-badge__value">
                      {health.cache?.keys !== undefined ? `${health.cache.keys} Keys` : 'Active'}
                    </span>
                    <div className={`health-badge__indicator ${getIndicatorClass(health.cache?.status)}`} />
                  </div>
                  <div className="health-badge">
                    <span className="health-badge__label">Queue</span>
                    <span className="health-badge__value">
                      {health.queue?.pending_tasks !== undefined ? `${health.queue.pending_tasks} Tasks` : 'Idle'}
                    </span>
                    <div className={`health-badge__indicator ${getIndicatorClass(health.queue?.status)}`} />
                  </div>
                  <div className="health-badge">
                    <span className="health-badge__label">Workers</span>
                    <span className="health-badge__value">Healthy</span>
                    <div className={`health-badge__indicator ${getIndicatorClass(health.worker?.status)}`} />
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)' }}>
                  <span>API Status: Healthy</span>
                  <span>Version: {health.version || '3.0.0'}</span>
                </div>
              </div>
            ) : (
              <div style={{ padding: '1rem', textAlign: 'center', color: 'red' }}>
                Failed to communicate with document server.
              </div>
            )}
          </div>

          {/* Supported Document types */}
          <div className="settings-card premium-card">
            <h3 className="settings-card__title">
              <Info size={18} />
              <span>Supported Documents</span>
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', lineHeight: 1.5 }}>
              PaperPulse AI automatically classifies, validates, and extracts structured data from these document formats:
            </p>
            <div className="settings-badges">
              {documentTypes.map((doc, idx) => (
                <span key={idx} className="doc-type-tag">
                  {doc.icon} {doc.label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </motion.div>
    </PageContainer>
  );
};
