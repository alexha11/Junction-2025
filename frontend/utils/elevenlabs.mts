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
    
    // Set volume to ensure it's audible and not muted
    audio.volume = 1.0;
    audio.muted = false;
    
    // Ensure audio context is active (resume if suspended)
    if (typeof AudioContext !== 'undefined') {
      try {
        const testContext = new AudioContext();
        if (testContext.state === 'suspended') {
          testContext.resume().then(() => {
            console.log("[TTS] AudioContext resumed");
          }).catch((err: unknown) => {
            console.warn("[TTS] Failed to resume AudioContext:", err);
          });
        }
      } catch (e) {
        console.warn("[TTS] Could not create AudioContext:", e);
      }
    }
    
    // Add to DOM temporarily to ensure it's connected (some browsers need this)
    audio.style.display = 'none';
    audio.setAttribute('preload', 'auto');
    document.body.appendChild(audio);
    
    audio.onloadeddata = () => {
      console.log("[TTS] Audio data loaded, duration:", audio.duration, "seconds");
      console.log("[TTS] Audio state:", {
        volume: audio.volume,
        muted: audio.muted,
        paused: audio.paused,
        readyState: audio.readyState,
      });
    };
    
    audio.oncanplay = () => {
      console.log("[TTS] Audio can play");
    };
    
    let playingConfirmed = false;
    audio.onplaying = () => {
      playingConfirmed = true;
      console.log("[TTS] 🔊 Audio is now PLAYING (should hear sound now)");
      console.log("[TTS] Audio playback state:", {
        currentTime: audio.currentTime,
        duration: audio.duration,
        paused: audio.paused,
        volume: audio.volume,
        muted: audio.muted,
        src: url.substring(0, 50) + "...",
      });
      
      // Check system audio context
      if (typeof AudioContext !== 'undefined') {
        const audioContext = new AudioContext();
        console.log("[TTS] AudioContext state:", audioContext.state);
        if (audioContext.state === 'suspended') {
          console.warn("[TTS] ⚠️ AudioContext is suspended - user interaction may be required");
        }
      }
    };
    
    audio.ontimeupdate = () => {
      // Log progress every second to confirm it's actually playing
      if (Math.floor(audio.currentTime) % 1 === 0 && audio.currentTime > 0) {
        console.log(`[TTS] ⏱️ Playing: ${audio.currentTime.toFixed(1)}s / ${audio.duration.toFixed(1)}s`);
      }
    };
    
    audio.onended = () => {
      console.log("[TTS] Audio playback ended");
      document.body.removeChild(audio);
      URL.revokeObjectURL(url);
      resolve();
    };
    
    audio.onerror = (error) => {
      console.error("[TTS] Audio element error:", error);
      console.error("[TTS] Audio error details:", {
        code: audio.error?.code,
        message: audio.error?.message,
        MEDIA_ERR_ABORTED: audio.error?.code === 1,
        MEDIA_ERR_NETWORK: audio.error?.code === 2,
        MEDIA_ERR_DECODE: audio.error?.code === 3,
        MEDIA_ERR_SRC_NOT_SUPPORTED: audio.error?.code === 4,
      });
      if (document.body.contains(audio)) {
        document.body.removeChild(audio);
      }
      URL.revokeObjectURL(url);
      const errorMsg = audio.error ? 
        `Audio playback failed: ${audio.error.code} - ${audio.error.message}` :
        'Audio playback failed';
      reject(new Error(errorMsg));
    };
    
    audio.onpause = () => {
      console.warn("[TTS] ⚠️ Audio was paused (unexpected)");
    };
    
    audio.onstalled = () => {
      console.warn("[TTS] ⚠️ Audio playback stalled");
    };
    
    // Start playing - handle autoplay policy
    console.log("[TTS] Attempting to play audio...");
    console.log("[TTS] Pre-play state:", {
      volume: audio.volume,
      muted: audio.muted,
      paused: audio.paused,
      readyState: audio.readyState,
    });
    
    audio.play()
      .then(() => {
        console.log("[TTS] ✅ Audio play() promise resolved");
        // Double-check that it's actually playing
        setTimeout(() => {
          if (audio.paused) {
            console.error("[TTS] ❌ Audio play() resolved but audio is still paused!");
            console.error("[TTS] This might indicate a browser autoplay restriction or audio system issue");
            console.error("[TTS] Check browser tab audio settings and system volume");
          } else if (!playingConfirmed) {
            console.warn("[TTS] ⚠️ Audio play() resolved but 'playing' event not fired yet");
            console.warn("[TTS] Audio state:", {
              paused: audio.paused,
              currentTime: audio.currentTime,
              readyState: audio.readyState,
            });
          } else {
            console.log("[TTS] ✅ Confirmed: Audio is playing (not paused, playing event fired)");
          }
        }, 200);
      })
      .catch((playError) => {
        console.error("[TTS] ❌ Audio play() failed:", playError);
        if (document.body.contains(audio)) {
          document.body.removeChild(audio);
        }
        URL.revokeObjectURL(url);
        // Check if it's an autoplay policy error
        if (playError.name === 'NotAllowedError' || playError.message?.includes('play()')) {
          console.warn("[TTS] ⚠️ Autoplay blocked. User interaction required.");
          console.warn("[TTS] This is normal - browsers require user interaction before playing audio.");
          // Don't reject, just log - allow the system to continue
          resolve(); // Resolve instead of reject to not break the flow
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
