/**
 * AudioComparison component for A/B comparison of original vs recreation.
 * Per constitution X: Auto-play MUST be disabled by default.
 */

import { useState } from 'react';
import type { Iteration } from '../types/events';

interface AudioComparisonProps {
  sessionId: string;
  iterations: Iteration[];
}

export function AudioComparison({ sessionId, iterations }: AudioComparisonProps) {
  const [selectedIteration, setSelectedIteration] = useState<number>(
    iterations.length > 0 ? iterations[iterations.length - 1].number : 0
  );

  const completedIterations = iterations.filter(i => i.render_path);

  if (completedIterations.length === 0) {
    return (
      <div className="text-center text-gray-400 py-8">
        No completed iterations available for comparison yet.
      </div>
    );
  }

  const selectedIterationData = iterations.find(i => i.number === selectedIteration);
  const score = selectedIterationData?.evaluation?.total_score;
  const maxScore = selectedIterationData?.evaluation?.max_score || 60;

  return (
    <div className="space-y-6">
      {/* Iteration selector */}
      <div className="flex items-center justify-between">
        <label className="text-sm text-gray-400">Compare iteration:</label>
        <select
          value={selectedIteration}
          onChange={(e) => setSelectedIteration(Number(e.target.value))}
          className="bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm"
        >
          {completedIterations.map((iter) => (
            <option key={iter.number} value={iter.number}>
              Iteration #{iter.number}
              {iter.evaluation && ` (Score: ${iter.evaluation.total_score}/${iter.evaluation.max_score})`}
            </option>
          ))}
        </select>
      </div>

      {/* Side-by-side comparison */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Original */}
        <div className="bg-gray-700 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-semibold text-blue-400">Original</h4>
            <span className="text-xs text-gray-400 bg-gray-600 px-2 py-0.5 rounded">
              Reference
            </span>
          </div>
          <audio
            controls
            className="w-full"
            src={`/api/sessions/${sessionId}/audio/original`}
            preload="metadata"
          >
            Your browser does not support the audio element.
          </audio>
        </div>

        {/* Recreation */}
        <div className="bg-gray-700 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-semibold text-green-400">Recreation #{selectedIteration}</h4>
            {score !== undefined && (
              <span className={`text-xs px-2 py-0.5 rounded ${
                (score / maxScore) >= 0.8 ? 'bg-green-500/20 text-green-300' :
                (score / maxScore) >= 0.6 ? 'bg-yellow-500/20 text-yellow-300' :
                'bg-red-500/20 text-red-300'
              }`}>
                {score}/{maxScore}
              </span>
            )}
          </div>
          <audio
            controls
            className="w-full"
            src={`/api/sessions/${sessionId}/audio/iteration/${selectedIteration}`}
            preload="metadata"
          >
            Your browser does not support the audio element.
          </audio>
        </div>
      </div>

      {/* Tips */}
      <div className="text-xs text-gray-500 text-center">
        Tip: Use keyboard shortcuts to control playback. Click each player independently to compare.
      </div>
    </div>
  );
}
