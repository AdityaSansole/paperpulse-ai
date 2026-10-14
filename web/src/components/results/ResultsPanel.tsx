// ============================================================
// ResultsPanel — Tabbed Results Display Panel
// ============================================================

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Download, FileText, Database, Layers } from 'lucide-react';
import type { ExtractedDocument } from '@/api/types';
import { SummaryBox } from './SummaryBox';
import { FieldsGrid } from './FieldsGrid';
import { JsonViewer } from './JsonViewer';
import { ReviewNotes } from './ReviewNotes';
import { PeopleTable } from './PeopleTable';
import './ResultsPanel.css';

interface ResultsPanelProps {
  data: ExtractedDocument;
  downloadUrl?: string;
  rawJson: Record<string, unknown>;
}

type TabType = 'summary' | 'fields' | 'raw';

export const ResultsPanel: React.FC<ResultsPanelProps> = ({
  data,
  downloadUrl,
  rawJson,
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('summary');

  const people =
    'people' in data && Array.isArray((data as { people?: unknown }).people)
      ? ((data as { people?: Array<{ name?: string; date_of_birth?: string; id_number?: string; address?: string }> }).people ?? [])
      : [];

  const tabs = [
    { id: 'summary', label: 'Summary', icon: <FileText size={16} /> },
    { id: 'fields', label: 'Extracted Fields', icon: <Layers size={16} /> },
    { id: 'raw', label: 'Raw JSON', icon: <Database size={16} /> },
  ];

  return (
    <div className="results-panel premium-card">
      <div className="results-panel__tabs">
        <div className="results-panel__tab-list" role="tablist" aria-label="Extraction Results">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                aria-controls={`panel-${tab.id}`}
                id={`tab-${tab.id}`}
                className={`results-panel__tab-btn ${isActive ? 'results-panel__tab-btn--active' : ''}`}
                onClick={() => setActiveTab(tab.id as TabType)}
              >
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                  {tab.icon}
                  {tab.label}
                </span>
                {isActive && (
                  <motion.div
                    layoutId="activeTabUnderline"
                    className="results-panel__tab-indicator"
                    transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                  />
                )}
              </button>
            );
          })}
        </div>

        {downloadUrl && (
          <div className="results-panel__actions">
            <a
              href={downloadUrl}
              download="extracted_data.json"
              className="results-panel__download-btn"
              title="Download results as JSON file"
            >
              <Download size={14} />
              <span>Download JSON</span>
            </a>
          </div>
        )}
      </div>

      <div className="results-panel__content">
        <AnimatePresence mode="wait">
          {activeTab === 'summary' && (
            <motion.div
              key="summary"
              id="panel-summary"
              role="tabpanel"
              aria-labelledby="tab-summary"
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              transition={{ duration: 0.2 }}
              className="results-panel__pane"
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
                <SummaryBox data={data} />
                {data.review_notes && data.review_notes.length > 0 && (
                  <ReviewNotes notes={data.review_notes} needsReview={data.needs_review} />
                )}
                {people.length > 1 && <PeopleTable people={people} />}
              </div>
            </motion.div>
          )}

          {activeTab === 'fields' && (
            <motion.div
              key="fields"
              id="panel-fields"
              role="tabpanel"
              aria-labelledby="tab-fields"
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              transition={{ duration: 0.2 }}
              className="results-panel__pane"
            >
              <FieldsGrid data={data} />
            </motion.div>
          )}

          {activeTab === 'raw' && (
            <motion.div
              key="raw"
              id="panel-raw"
              role="tabpanel"
              aria-labelledby="tab-raw"
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              transition={{ duration: 0.2 }}
              className="results-panel__pane"
            >
              <JsonViewer data={rawJson} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};
