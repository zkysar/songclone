/**
 * FeedbackDisplay component shows evaluation results.
 * Displays score bars for 6 dimensions and prioritized feedback list.
 */

import type { EvaluationResult, FeedbackItem, Scores } from '../types/events';

interface FeedbackDisplayProps {
  evaluation: EvaluationResult;
}

interface ScoreBarProps {
  label: string;
  score: number;
  maxScore?: number;
}

function ScoreBar({ label, score, maxScore = 10 }: ScoreBarProps) {
  const percentage = (score / maxScore) * 100;

  const getBarColor = () => {
    if (percentage >= 80) return 'bg-green-500';
    if (percentage >= 60) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-gray-400 capitalize">{label}</span>
        <span className="font-medium">{score}/{maxScore}</span>
      </div>
      <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${getBarColor()} transition-all duration-500`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

function FeedbackItemDisplay({ item }: { item: FeedbackItem }) {
  const categoryColors: Record<string, string> = {
    timing: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    harmony: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
    melody: 'bg-pink-500/20 text-pink-300 border-pink-500/30',
    instruments: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
    mix: 'bg-green-500/20 text-green-300 border-green-500/30',
    other: 'bg-gray-500/20 text-gray-300 border-gray-500/30',
  };

  const priorityBadge = () => {
    if (item.priority === 1) return { bg: 'bg-red-500', text: 'P1' };
    if (item.priority === 2) return { bg: 'bg-orange-500', text: 'P2' };
    if (item.priority === 3) return { bg: 'bg-yellow-500', text: 'P3' };
    return { bg: 'bg-gray-500', text: `P${item.priority}` };
  };

  const badge = priorityBadge();

  return (
    <div className={`border rounded-lg p-3 ${categoryColors[item.category] || categoryColors.other}`}>
      <div className="flex items-start gap-2">
        <span className={`${badge.bg} text-white text-xs font-bold px-1.5 py-0.5 rounded`}>
          {badge.text}
        </span>
        <div className="flex-1 space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium uppercase opacity-70">{item.category}</span>
          </div>
          <p className="text-sm font-medium">{item.issue}</p>
          <p className="text-xs opacity-80">
            <span className="font-medium">Suggestion: </span>
            {item.suggestion}
          </p>
        </div>
      </div>
    </div>
  );
}

export function FeedbackDisplay({ evaluation }: FeedbackDisplayProps) {
  const scores: { key: keyof Scores; label: string }[] = [
    { key: 'timing', label: 'Timing' },
    { key: 'harmony', label: 'Harmony' },
    { key: 'melody', label: 'Melody' },
    { key: 'instruments', label: 'Instruments' },
    { key: 'mix', label: 'Mix' },
    { key: 'overall', label: 'Overall' },
  ];

  const totalPercentage = (evaluation.total_score / evaluation.max_score) * 100;

  return (
    <div className="space-y-6">
      {/* Overall score */}
      <div className="bg-gray-700 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-lg font-semibold">Overall Score</h4>
          <div className="flex items-center gap-2">
            <span className={`text-2xl font-bold ${totalPercentage >= 80 ? 'text-green-400' : totalPercentage >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
              {evaluation.total_score}
            </span>
            <span className="text-gray-400">/ {evaluation.max_score}</span>
          </div>
        </div>
        <div className="h-3 bg-gray-600 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-700 ${totalPercentage >= 80 ? 'bg-green-500' : totalPercentage >= 60 ? 'bg-yellow-500' : 'bg-red-500'}`}
            style={{ width: `${totalPercentage}%` }}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-sm">
          <span className="text-gray-400">
            {evaluation.evaluation_method === 'ai' ? 'AI Evaluation' : 'MFCC Fallback'}
          </span>
          {evaluation.stop_early && (
            <span className="text-green-400 font-medium">
              {'\u2713'} Quality threshold reached!
            </span>
          )}
        </div>
      </div>

      {/* Dimension scores */}
      <div>
        <h4 className="text-sm font-semibold text-gray-400 mb-3">Dimension Scores</h4>
        <div className="grid grid-cols-2 gap-4">
          {scores.map(({ key, label }) => (
            <ScoreBar
              key={key}
              label={label}
              score={evaluation.scores[key]}
            />
          ))}
        </div>
      </div>

      {/* Feedback items */}
      {evaluation.feedback.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-gray-400 mb-3">
            Feedback ({evaluation.feedback.length} items)
          </h4>
          <div className="space-y-2">
            {evaluation.feedback
              .sort((a, b) => a.priority - b.priority)
              .map((item, index) => (
                <FeedbackItemDisplay key={index} item={item} />
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
