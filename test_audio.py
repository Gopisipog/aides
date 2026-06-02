import sys; sys.path.insert(0, '.')
from src.ingestion.live_audio import list_audio_devices
d = list_audio_devices()
print(f'Devices: {len(d)}')
for x in d[:5]:
    print(f'  [{x["index"]}] {x["name"]}  ch:{x["channels"]} sr:{x["samplerate"]}')
