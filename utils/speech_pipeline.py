import asyncio
import urllib.parse
import requests
import io
from queue import Queue
from threading import Thread
from pydub import AudioSegment
import simpleaudio as sa
from utils.translate import translate_google, detect_google
from utils.subtitle import generate_subtitle
from utils.katakana import katakana_converter
from datetime import datetime
from config import VOICEVOX_BASE_URL
def now():
    return datetime.now().strftime("[%H:%M:%S]")

# Hàng đợi âm thanh (public để run.py khởi động playback worker)
audio_queue = Queue()

def get_voicevox_audio_bytes(tts):
    try:
        voicevox_url = VOICEVOX_BASE_URL
        katakana_text = katakana_converter(tts)
        params = urllib.parse.urlencode({'text': katakana_text, 'speaker': 46})
        res_query = requests.post(f'{voicevox_url}/audio_query?{params}')
        res_query.raise_for_status()

        synth_params = urllib.parse.urlencode({'speaker': 46, 'enable_interrogative_upspeak': True})
        res_synth = requests.post(f'{voicevox_url}/synthesis?{synth_params}', json=res_query.json())
        res_synth.raise_for_status()

        return res_synth.content  # WAV bytes
    except Exception as e:
        print("❌ Voicevox async error:", e)
        return None
    
# Hàm async để xử lý dịch và gọi voicevox song song

async def process_ai_response_async(text, chat_now):
    print(f"{now()} [🌐 Translating] Detecting + translating: {text}")

    loop = asyncio.get_event_loop()
    detect_lang = await loop.run_in_executor(None, detect_google, text)

    future_ja = loop.run_in_executor(None, translate_google, text, detect_lang, "JA")
    future_en = loop.run_in_executor(None, translate_google, text, detect_lang, "EN")

    ja_text, en_text = await asyncio.gather(future_ja, future_en)

    print("JP Answer:", ja_text)
    print("EN Answer:", en_text)

    generate_subtitle(chat_now, text)
    print(f"{now()} [📝 Subtitle generated]")

    wav_bytes = await loop.run_in_executor(None, get_voicevox_audio_bytes, ja_text)
    if wav_bytes:
        audio_queue.put(wav_bytes)
    print(f"{now()} [🔊 VoiceVox done] Queued audio for playback.")


def playback_worker(running_flag):

    while running_flag():
        try:
            wav_bytes = audio_queue.get()
            print(f"{now()} [🎵 PLAYING AUDIO]")

            audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
            playback = sa.play_buffer(
                audio.raw_data,
                num_channels=audio.channels,
                bytes_per_sample=audio.sample_width,
                sample_rate=audio.frame_rate
            )
            playback.wait_done()
        except Exception as e:
            print("⚠️ Playback error:", e)
