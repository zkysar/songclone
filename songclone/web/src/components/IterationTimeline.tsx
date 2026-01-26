/**
 * IterationTimeline component displays horizontal timeline of iterations.
 * Shows status indicators, score badges, and allows selection for detail view.
 */

import type { Iteration } from '../types/events';

interface IterationTimelineProps {
  iterations: Iteration[];
  currentIteration: number;
  selectedIteration: number | null;
  onSelectIteration: (iterationNumber: number) => void;
}

function getStatusColor(status: Iteration['status']): string {
  switch (status) {
    case 'completed':
      return 'bg-green-500';
    case 'failed':
      return 'bg-red-500';
    case 'planning':
    case 'executing':
    case 'evaluating':
      return 'bg-yellow-500 animate-pulse';
    default:
      return 'bg-gray-500';
  }
}

function getStatusIcon(status: Iteration['status']): string {
  switch (status) {
    case 'completed':
      return '\u2713';
    case 'failed':
      return '\u2717';
    case 'planning':
      return '\ud83d\udcdd';
    case 'executing':
      return '\u25b6';
    case 'evaluating':
      return '\ud83d\udd0d';
    default:
      return '\u23f3';
  }
}

function getScoreColor(score: number, maxScore: number): string {
  const percentage = (score / maxScore) * 100;
  if (percentage >= 80) return 'text-green-400';
  if (percentage >= 60) return 'text-yellow-400';
  return 'text-red-400';
}

export function IterationTimeline({
  iterations,
  currentIteration,
  selectedIteration,
  onSelectIteration,
}: IterationTimelineProps) {
  if (iterations.length === 0) {
    return (
      <div className="text-center text-gray-400 py-8">
        No iterations yet. Recreation will begin shortly...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Timeline */}
      <div className="flex items-center justify-start gap-2 overflow-x-auto pb-2">
        {iterations.map((iteration, index) => (
          <div key={iteration.number} className="flex items-center">
            {/* Iteration card */}
            <button
              onClick={() => onSelectIteration(iteration.number)}
              className={`
                flex flex-col items-center p-3 rounded-lg min-w-[100px] transition-all
                ${selectedIteration === iteration.number
                  ? 'bg-blue-600 ring-2 ring-blue-400'
                  : 'bg-gray-700 hover:bg-gray-600'}
              `}
            >
              {/* Status indicator */}
              <div className={`w-8 h-8 rounded-full flex items-center justify-center ${getStatusColor(iteration.status)}`}>
                <span className="text-white text-sm">{getStatusIcon(iteration.status)}</span>
              </div>

              {/* Iteration number */}
              <span className="text-sm font-medium mt-1">
                #{iteration.number}
              </span>

              {/* Score badge */}
              {iteration.evaluation && (
                <span className={`text-xs font-bold ${getScoreColor(iteration.evaluation.total_score, iteration.evaluation.max_score)}`}>
                  {iteration.evaluation.total_score}/{iteration.evaluation.max_score}
                </span>
              )}

              {/* Status text */}
              <span className="text-xs text-gray-400 capitalize">
                {iteration.status}
              </span>
            </button>

            {/* Connector line */}
            {index < iterations.length - 1 && (
              <div className="w-4 h-0.5 bg-gray-600 mx-1" />
            )}
          </div>
        ))}

        {/* Show pending indicator if still iterating */}
        {currentIteration > iterations.length && (
          <div className="flex items-center">
            <div className="w-4 h-0.5 bg-gray-600 mx-1" />
            <div className="flex flex-col items-center p-3 rounded-lg min-w-[100px] bg-gray-700/50 border border-dashed border-gray-500">
              <div className="w-8 h-8 rounded-full flex items-center justify-center bg-gray-600 animate-pulse">
                <span className="text-white text-sm">{'\u23f3'}</span>
              </div>
              <span className="text-sm font-medium mt-1 text-gray-400">
                #{currentIteration}
              </span>
              <span className="text-xs text-gray-500">
                In Progress
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Summary stats */}
      <div className="flex gap-4 text-sm text-gray-400">
        <span>Total: {iterations.length} iterations</span>
        {iterations.length > 0 && iterations[iterations.length - 1].evaluation && (
          <span>
            Best Score: {Math.max(...iterations.filter(i => i.evaluation).map(i => i.evaluation!.total_score))}/60
          </span>
        )}
      </div>
    </div>
  );
}
