// ============================================================
// Page — Home (Single Document Upload & Results)
// ============================================================

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FileSearch } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { DropZone } from '@/components/upload/DropZone';
import { FilePreview } from '@/components/upload/FilePreview';
import { UploadButton } from '@/components/upload/UploadButton';
import { StatusBanner } from '@/components/upload/StatusBanner';
import { ProcessingSteps } from '@/components/progress/ProcessingSteps';
import { ResultsPanel } from '@/components/results/ResultsPanel';
import { useUpload } from '@/api/hooks/useUpload';
import './HomePage.css';

const easeOutExpo = [0.16, 1, 0.3, 1] as const;

const pageTransition = {
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -24 },
  transition: { duration: 0.35, ease: easeOutExpo },
};

const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4 } },
};

const resultVariants = {
  hidden: { opacity: 0, x: 40, scale: 0.97 },
  visible: {
    opacity: 1,
    x: 0,
    scale: 1,
    transition: { duration: 0.5, ease: easeOutExpo },
  },
  exit: {
    opacity: 0,
    x: -20,
    transition: { duration: 0.3 },
  },
};

export const HomePage: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  
  const {
    state,
    upload,
    reset,
  } = useUpload();

  const { status, result, error, step } = state;

  const isIdle = status === 'idle';
  const isProcessing = status === 'processing';
  const isComplete = status === 'completed';
  const isFailed = status === 'failed';

  const handleFileSelect = (file: File) => {
    setSelectedFile(file);
    reset(); // Reset upload state on new file selection
  };

  const handleFileRemove = () => {
    setSelectedFile(null);
    reset();
  };

  const handleUpload = () => {
    if (selectedFile) {
      upload(selectedFile);
    }
  };

  return (
    <motion.div {...pageTransition}>
      <PageContainer
        title="PaperPulse AI"
        subtitle="AI-powered document extraction and analysis"
      >
        <div className="home-page">
          <div className="home-page__layout">
            {/* ---- Upload Section (Left / Top) ---- */}
            <motion.div
              className="home-page__upload"
              variants={cardVariants}
              initial="hidden"
              animate="visible"
            >
              <div className="home-page__upload-card premium-card">
                <span className="home-page__section-title section-label" style={{ display: 'block', marginBottom: '16px' }}>
                  Upload Document
                </span>

                <DropZone onFileSelect={handleFileSelect} disabled={isProcessing} />

                <AnimatePresence mode="wait">
                  {selectedFile && (
                    <motion.div
                      key="file-preview"
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.3 }}
                      style={{ overflow: 'hidden' }}
                    >
                      <FilePreview
                        file={selectedFile}
                        onRemove={handleFileRemove}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>

                <div className="home-page__actions" style={{ marginTop: '20px' }}>
                  <UploadButton
                    state={isProcessing ? 'loading' : (selectedFile ? 'ready' : 'disabled')}
                    onClick={handleUpload}
                  />
                </div>
              </div>

              {/* Status / Error Banner */}
              <AnimatePresence mode="wait">
                {(error || isFailed) && (
                  <motion.div
                    className="home-page__status"
                    key="status-banner"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.25 }}
                    style={{ marginTop: '16px' }}
                  >
                    <StatusBanner
                      type="error"
                      message={error || 'Processing failed. Please try again.'}
                      onDismiss={reset}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>

            {/* ---- Results Section (Right / Bottom) ---- */}
            <div className="home-page__results" aria-live="polite">
              <AnimatePresence mode="wait">
                {isIdle && !result && (
                  <motion.div
                    key="placeholder"
                    className="home-page__results-placeholder premium-card"
                    variants={resultVariants}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                  >
                    <div className="home-page__placeholder-icon">
                      <FileSearch size={36} />
                    </div>
                    <h3 className="home-page__placeholder-title">
                      No document processed yet
                    </h3>
                    <p className="home-page__placeholder-text">
                      Upload a PDF or image to extract structured data using
                      AI-powered document intelligence.
                    </p>
                  </motion.div>
                )}

                {isProcessing && (
                  <motion.div
                    key="processing"
                    className="home-page__processing premium-card"
                    variants={resultVariants}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                    style={{ padding: '24px' }}
                  >
                    <ProcessingSteps
                      status={status}
                      currentStep={Math.max(0, step - 1)}
                    />
                  </motion.div>
                )}

                {isComplete && result && (
                  <motion.div
                    key="results"
                    variants={resultVariants}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                  >
                    <ResultsPanel
                      data={result.extracted_data}
                      rawJson={result.raw_response}
                      downloadUrl={result.download_url}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </PageContainer>
    </motion.div>
  );
};
export default HomePage;
