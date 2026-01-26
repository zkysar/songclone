/**
 * IterationDetail component shows full details for a selected iteration.
 * Combines plan viewer, audio player, and feedback display.
 */

import { useState } from 'react';
import type { Iteration } from '../types/events';
import { PlanViewer } from './PlanViewer';
import { FeedbackDisplay } from './FeedbackDisplay';
import { AudioPlayer } from './AudioPlayer';

interface IterationDetailProps {
  iteration: Iteration;
  sessionId: string;
}

type TabType = 'plan' | 'audio' | 'feedback';

export function IterationDetail({ iteration, sessionId }: IterationDetailProps) {
  const [activeTab, setActiveTab] = useState<TabType>('audio');

  const tabs: { id: TabType; label: string; disabled: boolean }[] = [
    { id: 'audio', label: 'Audio', disabled: !iteration.render_path },
    { id: 'plan', label: 'Plan', disabled: false },
    { id: 'feedback', label: 'Feedback', disabled: !iteration.evaluation },
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Iteration #{iteration.number}</h3>
        <div className="flex items-center gap-2 text-sm">
          <span className={`
            px-2 py-0.5 rounded capitalize
            ${iteration.status === 'completed' ? 'bg-green-500/20 text-green-300' :
              iteration.status === 'failed' ? 'bg-red-500/20 text-red-300' :
              'bg-yellow-500/20 text-yellow-300'}
          `}>
            {iteration.status}
          </span>
          {iteration.evaluation && (
            <span className="text-gray-400">
              Score: <span className="text-white font-medium">
                {iteration.evaluation.total_score}/{iteration.evaluation.max_score}
              </span>
            </span>
          )}
        </div>
      </div>

      {/* Tab navigation */}
      <div className="flex border-b border-gray-600">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => !tab.disabled && setActiveTab(tab.id)}
            disabled={tab.disabled}
            className={`
              px-4 py-2 text-sm font-medium border-b-2 transition-colors
              ${activeTab === tab.id
                ? 'border-blue-500 text-blue-400'
                : tab.disabled
                  ? 'border-transparent text-gray-600 cursor-not-allowed'
                  : 'border-transparent text-gray-400 hover:text-gray-200'}
            `}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="min-h-[200px]">
        {activeTab === 'audio' && (
          iteration.render_path ? (
            <AudioPlayer
              sessionId={sessionId}
              iterationNumber={iteration.number}
              label="Recreation Audio"
            />
          ) : (
            <div className="text-center text-gray-400 py-8">
              Audio not yet available. Waiting for render to complete...
            </div>
          )
        )}

        {activeTab === 'plan' && (
          <PlanViewer plan={iteration.plan} />
        )}

        {activeTab === 'feedback' && (
          iteration.evaluation ? (
            <FeedbackDisplay evaluation={iteration.evaluation} />
          ) : (
            <div className="text-center text-gray-400 py-8">
              Evaluation not yet available. Waiting for evaluation to complete...
            </div>
          )
        )}
      </div>
    </div>
  );
}
