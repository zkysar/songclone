/**
 * HumanActionRequired component displays when manual intervention is needed.
 * Shows instructions and provides resume/cancel options.
 */

interface HumanActionRequiredProps {
  description: string;
  reason: string;
  steps: string[];
  sessionId: string;
  onResume: () => void;
  onCancel: () => void;
}

export function HumanActionRequired({
  description,
  reason,
  steps,
  sessionId,
  onResume,
  onCancel,
}: HumanActionRequiredProps) {
  return (
    <div className="bg-yellow-500/10 border border-yellow-500 rounded-lg p-6 space-y-4">
      <div className="flex items-start gap-3">
        <div className="text-yellow-500 text-2xl">{'\u26a0\ufe0f'}</div>
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-yellow-400">
            Manual Action Required
          </h3>
          <p className="text-gray-300 mt-1">{description}</p>
        </div>
      </div>

      <div className="bg-gray-800/50 rounded p-4 space-y-3">
        <div>
          <span className="text-sm text-gray-400">Reason: </span>
          <span className="text-sm text-gray-200">{reason}</span>
        </div>

        <div>
          <h4 className="text-sm font-medium text-gray-400 mb-2">Steps to complete:</h4>
          <ol className="list-decimal list-inside space-y-1 text-sm">
            {steps.map((step, index) => (
              <li key={index} className="text-gray-200">{step}</li>
            ))}
          </ol>
        </div>
      </div>

      <div className="flex gap-3">
        <button
          onClick={onResume}
          className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-white font-medium transition-colors"
        >
          I've Completed the Action - Resume
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded text-white transition-colors"
        >
          Cancel Session
        </button>
      </div>

      <p className="text-xs text-gray-500 text-center">
        Session ID: {sessionId.slice(0, 8)}...
      </p>
    </div>
  );
}
