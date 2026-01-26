/**
 * Drag-and-drop upload area for audio files.
 */

import { useCallback, useState } from 'react';

interface UploadAreaProps {
  onUpload: (file: File, maxIterations: number, qualityThreshold: number) => Promise<void>;
  isUploading: boolean;
}

const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB
const ALLOWED_TYPES = ['audio/wav', 'audio/mpeg', 'audio/mp3', 'audio/x-wav'];

export function UploadArea({ onUpload, isUploading }: UploadAreaProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [maxIterations, setMaxIterations] = useState(10);
  const [qualityThreshold, setQualityThreshold] = useState(0.8);

  const validateFile = useCallback((file: File): string | null => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      return 'Invalid file type. Please upload a WAV or MP3 file.';
    }
    if (file.size > MAX_FILE_SIZE) {
      return 'File too large. Maximum size is 100MB.';
    }
    return null;
  }, []);

  const handleFile = useCallback(
    async (file: File) => {
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }

      setError(null);
      await onUpload(file, maxIterations, qualityThreshold);
    },
    [validateFile, onUpload, maxIterations, qualityThreshold]
  );

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);

      const file = e.dataTransfer.files[0];
      if (file) {
        await handleFile(file);
      }
    },
    [handleFile]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleInputChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        await handleFile(file);
      }
    },
    [handleFile]
  );

  return (
    <div className="space-y-4">
      <div
        className={`
          border-2 border-dashed rounded-lg p-8 text-center transition-colors
          ${isDragging ? 'border-blue-500 bg-blue-500/10' : 'border-gray-600 hover:border-gray-500'}
          ${isUploading ? 'opacity-50 pointer-events-none' : 'cursor-pointer'}
        `}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => document.getElementById('file-input')?.click()}
      >
        <input
          id="file-input"
          type="file"
          accept=".wav,.mp3,audio/wav,audio/mpeg"
          onChange={handleInputChange}
          className="hidden"
          disabled={isUploading}
        />

        {isUploading ? (
          <div className="space-y-2">
            <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto" />
            <p className="text-gray-400">Uploading...</p>
          </div>
        ) : (
          <div className="space-y-2">
            <svg
              className="w-12 h-12 mx-auto text-gray-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            <p className="text-gray-300">
              Drag and drop an audio file, or click to browse
            </p>
            <p className="text-sm text-gray-500">
              WAV or MP3, max 10 minutes
            </p>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500 rounded p-3 text-red-400">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Max Iterations
          </label>
          <input
            type="number"
            min={1}
            max={20}
            value={maxIterations}
            onChange={(e) => setMaxIterations(Number(e.target.value))}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
            disabled={isUploading}
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Quality Threshold
          </label>
          <input
            type="number"
            min={0}
            max={1}
            step={0.1}
            value={qualityThreshold}
            onChange={(e) => setQualityThreshold(Number(e.target.value))}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
            disabled={isUploading}
          />
        </div>
      </div>
    </div>
  );
}
