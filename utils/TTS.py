import os
import torch
import requests
import urllib.parse
from utils.katakana import *
import json
from pydub import AudioSegment
import simpleaudio as sa
import io
from config import VOICEVOX_BASE_URL

# https://github.com/snakers4/silero-models#text-to-speech
def silero_tts(tts, language, model, speaker):
    device = torch.device('cpu')
    torch.set_num_threads(4)
    local_file = 'model.pt'

    if not os.path.isfile(local_file):
        torch.hub.download_url_to_file(f'https://models.silero.ai/models/tts/{language}/{model}.pt',
                                    local_file)  

    model = torch.package.PackageImporter(local_file).load_pickle("tts_models", "model")
    model.to(device)

    example_text = "i'm fine thank you and you?"
    sample_rate = 48000

    audio_paths = model.save_wav(text=tts,
                                speaker=speaker,
                                sample_rate=sample_rate)
    

def voicevox_tts(tts, use_memory=True):
    voicevox_url =VOICEVOX_BASE_URL
    katakana_text = katakana_converter(tts)

    try:
        params_encoded = urllib.parse.urlencode({'text': katakana_text, 'speaker': 46})
        response_query  = requests.post(f'{voicevox_url}/audio_query?{params_encoded}')
        response_query.raise_for_status()

        synthesis_params = urllib.parse.urlencode({'speaker': 46, 'enable_interrogative_upspeak': True})
        response_synth = requests.post(
            f'{voicevox_url}/synthesis?{synthesis_params}',
            json=response_query.json()
        )
        response_synth.raise_for_status()

        if use_memory:
            # Phát trực tiếp từ bộ nhớ
            audio = AudioSegment.from_file(io.BytesIO(response_synth.content), format="wav")
            playback = sa.play_buffer(
                audio.raw_data,
                num_channels=audio.channels,
                bytes_per_sample=audio.sample_width,
                sample_rate=audio.frame_rate
            )
            playback.wait_done()
        else:
            # Lưu file và để run.py dùng winsound
            with open("test.wav", "wb") as outfile:
                outfile.write(response_synth.content)

    except Exception as e:
        print("❌ Voicevox error:", e)

if __name__ == "__main__":
    silero_tts()
