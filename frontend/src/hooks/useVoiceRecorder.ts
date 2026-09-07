import { useCallback, useRef, useState } from "react";

type RecorderStatus = "idle" | "recording" | "processing";

/** Records a short voice note from the browser's microphone via
 * MediaRecorder. Owns only the capture - uploading the resulting blob and
 * showing the transcript is the caller's job (useWebChat.sendVoiceNote). */
export function useVoiceRecorder(onRecorded: (blob: Blob) => Promise<void>) {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        setStatus("processing");
        try {
          const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
          await onRecorded(blob);
        } catch (e) {
          setError(e instanceof Error ? e.message : "could not send voice note");
        } finally {
          setStatus("idle");
        }
      };

      recorderRef.current = recorder;
      recorder.start();
      setStatus("recording");
    } catch {
      setError("microphone access denied or unavailable");
    }
  }, [onRecorded]);

  const stop = useCallback(() => {
    recorderRef.current?.stop();
  }, []);

  return { status, error, start, stop };
}
