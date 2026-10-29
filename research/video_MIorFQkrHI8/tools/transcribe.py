import sys
from faster_whisper import WhisperModel
src, out = sys.argv[1], sys.argv[2]
model = WhisperModel("small.en", device="cpu", compute_type="int8")
import numpy as np
audio = np.fromfile(src, dtype=np.int16).astype(np.float32) / 32768.0
segs, _ = model.transcribe(audio, beam_size=5, word_timestamps=False)
with open(out, "w", encoding="utf8") as f:
    for s in segs:
        line = f"[{s.start:5.1f}-{s.end:5.1f}] {s.text.strip()}"
        print(line); f.write(line + "\n")
