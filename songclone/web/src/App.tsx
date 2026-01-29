/**
 * Main application component for SongClone.
 * Per constitution X: Auto-play MUST be disabled by default.
 */

import { useCallback, useEffect, useState } from 'react';
import { UploadArea } from './components/UploadArea';
import { EventLog } from './components/EventLog';
import { Timeline } from './components/Timeline';
import { IterationTimeline } from './components/IterationTimeline';
import { IterationDetail } from './components/IterationDetail';
import { AudioComparison } from './components/AudioComparison';
import { HumanActionRequired } from './components/HumanActionRequired';
import { useSSE } from './hooks/useSSE';
import type { Iteration, Session, SSEEvent } from './types/events';
import {
  isAudioEvent,
  isCompleteEvent,
  isErrorEvent,
  isHumanActionEvent,
  isIterationEvent,
  isPhaseEvent,
  isStepEvent,
} from './types/events';

type AppState = 'idle' | 'uploading' | 'analyzing' | 'iterating' | 'complete' | 'error';
type ViewMode = 'timeline' | 'log';

function App() {
  const [appState, setAppState] = useState<AppState>('idle');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [iterations, setIterations] = useState<Iteration[]>([]);
  const [currentIteration, setCurrentIteration] = useState(0);
  const [selectedIteration, setSelectedIteration] = useState<number | null>(null);
  const [showComparison, setShowComparison] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('timeline');
  const [humanAction, setHumanAction] = useState<{
    description: string;
    reason: string;
    steps: string[];
  } | null>(null);

  // Load existing session on mount if URL has session param
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionParam = params.get('session');
    if (sessionParam) {
      setSessionId(sessionParam);
      // Fetch existing session data
      fetch(`/api/sessions/${sessionParam}`)
        .then(res => res.json())
        .then((session: Session) => {
          setIterations(session.iterations);
          setCurrentIteration(session.current_iteration);
          if (session.iterations.length > 0) {
            setSelectedIteration(session.iterations[session.iterations.length - 1].number);
          }
          if (session.status === 'completed' || session.status === 'cancelled') {
            setAppState('complete');
          } else if (session.status === 'iterating') {
            setAppState('iterating');
          } else if (session.status === 'analyzing') {
            setAppState('analyzing');
          } else if (session.status === 'failed') {
            setAppState('error');
            setErrorMessage(session.error || 'Session failed');
          }
        })
        .catch(err => {
          console.error('Failed to load session:', err);
          setAppState('error');
          setErrorMessage('Failed to load session');
        });
    }
  }, []);

  const handleEvent = useCallback((event: SSEEvent) => {
    if (isPhaseEvent(event)) {
      if (event.phase === 'analysis' && event.status === 'complete') {
        setAppState('iterating');
      }
    } else if (isIterationEvent(event)) {
      if (event.status === 'started') {
        setCurrentIteration(event.number);
      }
    } else if (isStepEvent(event)) {
      if (event.step === 'planning' && event.status === 'complete' && event.data) {
        // New iteration started with plan data - add placeholder iteration
        const planData = event.data as { reasoning: string; track_count: number };
        const newIteration: Iteration = {
          number: currentIteration,
          plan: {
            reasoning: planData.reasoning,
            tracks: [],
            master_fx: [],
          },
          render_path: null,
          evaluation: null,
          started_at: new Date().toISOString(),
          completed_at: null,
          status: 'executing',
        };
        setIterations(prev => {
          const existing = prev.find(i => i.number === currentIteration);
          if (existing) return prev;
          return [...prev, newIteration];
        });
        setSelectedIteration(currentIteration);
      }
    } else if (isAudioEvent(event)) {
      // Update iteration with render path
      setIterations(prev =>
        prev.map(iter =>
          iter.number === event.iteration
            ? { ...iter, render_path: event.path, status: 'evaluating' }
            : iter
        )
      );
    } else if (isHumanActionEvent(event)) {
      setHumanAction({
        description: event.description,
        reason: event.reason,
        steps: event.steps,
      });
      setAppState('iterating'); // Keep in iterating state but paused
    } else if (isCompleteEvent(event)) {
      setAppState('complete');
      setHumanAction(null);
      // Refresh session to get final iteration data
      if (sessionId) {
        fetch(`/api/sessions/${sessionId}`)
          .then(res => res.json())
          .then((session: Session) => {
            setIterations(session.iterations);
          })
          .catch(console.error);
      }
    } else if (isErrorEvent(event)) {
      if (!event.recoverable) {
        setAppState('error');
        setErrorMessage(event.message);
      }
    }
  }, [currentIteration, sessionId]);

  const { events, isConnected, error: sseError } = useSSE({
    sessionId,
    onEvent: handleEvent,
  });

  const handleUpload = useCallback(
    async (file: File, maxIterations: number, qualityThreshold: number) => {
      setAppState('uploading');
      setErrorMessage(null);

      const formData = new FormData();
      formData.append('audio', file);
      formData.append('max_iterations', maxIterations.toString());
      formData.append('quality_threshold', qualityThreshold.toString());

      try {
        const response = await fetch('/api/sessions', {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Upload failed');
        }

        const data = await response.json();
        setSessionId(data.session_id);
        setAppState('analyzing');

        window.history.pushState({}, '', `?session=${data.session_id}`);
      } catch (err) {
        setAppState('error');
        setErrorMessage(err instanceof Error ? err.message : 'Upload failed');
      }
    },
    []
  );

  const handleCancel = useCallback(async () => {
    if (!sessionId) return;

    try {
      await fetch(`/api/sessions/${sessionId}/cancel`, { method: 'POST' });
      setAppState('complete');
      setHumanAction(null);
    } catch (err) {
      console.error('Cancel failed:', err);
    }
  }, [sessionId]);

  const handleResume = useCallback(async () => {
    if (!sessionId) return;

    try {
      await fetch(`/api/sessions/${sessionId}/resume`, { method: 'POST' });
      setHumanAction(null);
    } catch (err) {
      console.error('Resume failed:', err);
    }
  }, [sessionId]);

  const getStatusText = () => {
    switch (appState) {
      case 'uploading':
        return 'Uploading audio...';
      case 'analyzing':
        return 'Analyzing song...';
      case 'iterating':
        return 'Recreating song...';
      case 'complete':
        return 'Complete!';
      case 'error':
        return 'Error';
      default:
        return 'Upload a song to begin';
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <header className="p-4 border-b border-gray-700">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">SongClone</h1>
            <p className="text-gray-400">AI-powered song recreation</p>
          </div>
          {sessionId && (
            <div className="flex items-center gap-4">
              <span
                className={`w-2 h-2 rounded-full ${
                  isConnected ? 'bg-green-500' : 'bg-red-500'
                }`}
              />
              <span className="text-sm text-gray-400">
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
          )}
        </div>
      </header>

      <main className="max-w-4xl mx-auto p-4 space-y-6">
        <div className="bg-gray-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">{getStatusText()}</h2>
            {(appState === 'analyzing' || appState === 'iterating') && (
              <button
                onClick={handleCancel}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded text-sm"
              >
                Cancel
              </button>
            )}
          </div>

          {appState === 'idle' && (
            <UploadArea onUpload={handleUpload} isUploading={false} />
          )}

          {appState === 'uploading' && (
            <UploadArea onUpload={handleUpload} isUploading={true} />
          )}

          {appState === 'error' && (
            <div className="space-y-4">
              <div className="bg-red-500/10 border border-red-500 rounded p-4 text-red-400">
                {errorMessage || sseError || 'An error occurred'}
              </div>
              <button
                onClick={() => {
                  setAppState('idle');
                  setSessionId(null);
                  setErrorMessage(null);
                  window.history.pushState({}, '', '/');
                }}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded"
              >
                Start Over
              </button>
            </div>
          )}

          {appState === 'complete' && (
            <div className="space-y-4">
              <div className="bg-green-500/10 border border-green-500 rounded p-4 text-green-400">
                Recreation complete!
              </div>
              {sessionId && (
                <a
                  href={`/api/sessions/${sessionId}/download`}
                  className="inline-block px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded"
                >
                  Download Best Result
                </a>
              )}
            </div>
          )}

          {/* Human Action Required Panel */}
          {humanAction && sessionId && (
            <HumanActionRequired
              description={humanAction.description}
              reason={humanAction.reason}
              steps={humanAction.steps}
              sessionId={sessionId}
              onResume={handleResume}
              onCancel={handleCancel}
            />
          )}
        </div>

        {(appState === 'analyzing' || appState === 'iterating' || appState === 'complete') && (
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Activity Log</h2>
              <div className="flex gap-2">
                <button
                  onClick={() => setViewMode('timeline')}
                  className={`px-3 py-1.5 text-sm rounded transition-colors ${
                    viewMode === 'timeline'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  Timeline
                </button>
                <button
                  onClick={() => setViewMode('log')}
                  className={`px-3 py-1.5 text-sm rounded transition-colors ${
                    viewMode === 'log'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  Simple Log
                </button>
              </div>
            </div>
            {viewMode === 'timeline' ? (
              <Timeline events={events} />
            ) : (
              <EventLog events={events} />
            )}
          </div>
        )}

        {sessionId && (appState === 'analyzing' || appState === 'iterating' || appState === 'complete') && (
          <div className="bg-gray-800 rounded-lg p-4">
            <h2 className="text-lg font-semibold mb-4">Original Audio</h2>
            <audio
              controls
              className="w-full"
              src={`/api/sessions/${sessionId}/audio/original`}
            >
              Your browser does not support the audio element.
            </audio>
          </div>
        )}

        {/* Iteration Timeline */}
        {(appState === 'iterating' || appState === 'complete') && sessionId && (
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Recreation Iterations</h2>
              {iterations.some(i => i.render_path) && (
                <button
                  onClick={() => setShowComparison(!showComparison)}
                  className={`px-3 py-1.5 text-sm rounded transition-colors ${
                    showComparison
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {showComparison ? 'Hide Comparison' : 'Compare Audio'}
                </button>
              )}
            </div>
            <IterationTimeline
              iterations={iterations}
              currentIteration={currentIteration}
              selectedIteration={selectedIteration}
              onSelectIteration={setSelectedIteration}
            />
          </div>
        )}

        {/* Audio Comparison Panel */}
        {showComparison && sessionId && iterations.length > 0 && (
          <div className="bg-gray-800 rounded-lg p-4">
            <h2 className="text-lg font-semibold mb-4">A/B Comparison</h2>
            <AudioComparison sessionId={sessionId} iterations={iterations} />
          </div>
        )}

        {/* Selected Iteration Detail */}
        {selectedIteration && sessionId && (
          <div className="bg-gray-800 rounded-lg p-4">
            {iterations.find(i => i.number === selectedIteration) && (
              <IterationDetail
                iteration={iterations.find(i => i.number === selectedIteration)!}
                sessionId={sessionId}
              />
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
