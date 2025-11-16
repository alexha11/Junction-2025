import { ElevenLabsClient } from '@elevenlabs/elevenlabs-js';

// Get API key from environment variable or use provided key
const ELEVENLABS_API_KEY = import.meta.env.VITE_ELEVENLABS_API_KEY || 'sk_c2fe89b82013aa96df453f8e20e0d1d0b9e8ca8736cf7344';

// Only initialize client if API key is provided and looks valid (ElevenLabs keys are typically long alphanumeric strings)
const hasValidApiKey = ELEVENLABS_API_KEY && ELEVENLABS_API_KEY.length > 20;

const elevenlabs = hasValidApiKey ? new ElevenLabsClient({
  apiKey: ELEVENLABS_API_KEY,
}) : null;

const DEFAULT_VOICE_ID = 'JBFqnCBsd6RMkjVDRZzb';
const DEFAULT_MODEL_ID = 'eleven_multilingual_v2';
const DEFAULT_OUTPUT_FORMAT = 'mp3_44100_128';

/**
 * Play audio stream in browser using Web Audio API
 */
async function playAudioStream(stream: ReadableStream<Uint8Array>): Promise<void> {
  // Collect all chunks from the stream
  const chunks: Uint8Array[] = [];
  const reader = stream.getReader();
  
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) {
        chunks.push(value);
      }
    }
  } finally {
    reader.releaseLock();
  }
  
  // Combine all chunks into a single Uint8Array
  const totalLength = chunks.reduce((acc, chunk) => acc + chunk.length, 0);
  const combined = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.length;
  }
  
  // Determine MIME type based on output format
  // Default to mp3, but could be adjusted based on DEFAULT_OUTPUT_FORMAT
  const mimeType = 'audio/mpeg'; // MP3 format
  
  // Create a Blob from the audio data
  const blob = new Blob([combined], { type: mimeType });
  const url = URL.createObjectURL(blob);
  
  // Play using HTML5 Audio
  return new Promise((resolve, reject) => {
    const audio = new Audio(url);
    
    audio.onended = () => {
      URL.revokeObjectURL(url);
      resolve();
    };
    
    audio.onerror = (error) => {
      URL.revokeObjectURL(url);
      const errorMsg = audio.error ? 
        `Audio playback failed: ${audio.error.code} - ${audio.error.message}` :
        'Audio playback failed';
      reject(new Error(errorMsg));
    };
    
    // Start playing - handle autoplay policy
    audio.play()
      .then(() => {
        console.log("[TTS] Audio playback started");
      })
      .catch((playError) => {
        URL.revokeObjectURL(url);
        // Check if it's an autoplay policy error
        if (playError.name === 'NotAllowedError') {
          console.warn("[TTS] Autoplay blocked. User interaction may be required.");
          reject(new Error("Audio playback blocked by browser autoplay policy. Please interact with the page first."));
        } else {
          reject(playError);
        }
      });
  });
}

/**
 * Play text using ElevenLabs TTS
 * Silently fails if API key is not configured or invalid
 */
export async function playText(text: string, voiceId: string = DEFAULT_VOICE_ID) {
  // Skip if no valid API key
  if (!hasValidApiKey || !elevenlabs) {
    console.warn("ElevenLabs TTS disabled: No valid API key configured. Set VITE_ELEVENLABS_API_KEY environment variable.");
    console.log("Current API key length:", ELEVENLABS_API_KEY?.length || 0);
    return;
  }

  if (!text || text.trim().length === 0) {
    console.debug("Skipping empty TTS text");
    return;
  }

  try {
    console.log(`[TTS] Requesting audio for text (${text.length} chars) with voice ${voiceId}`);
    const audioStream = await elevenlabs.textToSpeech.convert(voiceId, {
      text: text.trim(),
      modelId: DEFAULT_MODEL_ID,
      outputFormat: DEFAULT_OUTPUT_FORMAT,
    });

    console.log("[TTS] Audio stream received, playing...");
    await playAudioStream(audioStream);
    console.log("[TTS] Audio playback completed");
  } catch (error: any) {
    // Log all errors for debugging
    console.error("[TTS] Error details:", {
      message: error?.message,
      status: error?.status,
      detail: error?.detail,
      response: error?.response,
    });
    
    // Only log non-authentication errors to avoid spam
    if (error?.status !== 401 && error?.detail?.status !== 'invalid_api_key') {
      console.error("Error playing text:", error);
    } else {
      console.warn("ElevenLabs TTS authentication failed. Please check your API key.");
      console.log("API key used:", ELEVENLABS_API_KEY.substring(0, 10) + "...");
    }
  }
}
