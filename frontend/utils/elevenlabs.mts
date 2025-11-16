import { ElevenLabsClient, play } from '@elevenlabs/elevenlabs-js';

const elevenlabs = new ElevenLabsClient({
  apiKey: '',
});

const DEFAULT_VOICE_ID = 'JBFqnCBsd6RMkjVDRZzb';
const DEFAULT_MODEL_ID = 'eleven_multilingual_v2';
const DEFAULT_OUTPUT_FORMAT = 'mp3_44100_128';

/**
 * Converts a Node/Browser ReadableStream to AsyncIterable<Uint8Array>
 */
async function* streamToAsyncIterable(stream: ReadableStream<Uint8Array>): AsyncIterable<Uint8Array> {
  const reader = stream.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      yield value;
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Play text using ElevenLabs TTS
 */
export async function playText(text: string, voiceId: string = DEFAULT_VOICE_ID) {
  try {
    const audioStream = await elevenlabs.textToSpeech.convert(voiceId, {
      text,
      modelId: DEFAULT_MODEL_ID,
      outputFormat: DEFAULT_OUTPUT_FORMAT,
    });

    await play(streamToAsyncIterable(audioStream));
  } catch (error) {
    console.error("Error playing text:", error);
  }
}
