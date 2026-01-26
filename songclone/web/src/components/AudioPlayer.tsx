/**
 * AudioPlayer component for iteration renders.
 * Per constitution X: Auto-play MUST be disabled by default.
 */

interface AudioPlayerProps {
  sessionId: string;
  iterationNumber: number;
  label?: string;
}

export function AudioPlayer({ sessionId, iterationNumber, label }: AudioPlayerProps) {
  const audioUrl = `/api/sessions/${sessionId}/audio/iteration/${iterationNumber}`;

  return (
    <div className="bg-gray-700 rounded-lg p-4">
      {label && (
        <h4 className="text-sm font-medium text-gray-300 mb-2">{label}</h4>
      )}
      <audio
        controls
        className="w-full"
        src={audioUrl}
        preload="metadata"
      >
        Your browser does not support the audio element.
      </audio>
      <p className="text-xs text-gray-500 mt-1">
        Iteration #{iterationNumber} render
      </p>
    </div>
  );
}
