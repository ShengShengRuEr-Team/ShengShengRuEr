"""Decode a bounded evidence clip in the frozen processing environment."""

import argparse
import wave
from fractions import Fraction
from pathlib import Path


def extract(source, target, start_ms, end_ms):
    import av
    import numpy as np

    with av.open(str(source)) as container, wave.open(str(target), "wb") as output:
        stream = container.streams.audio[0]
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        container.seek(max(0, start_ms - 1000) * 1000, backward=True)
        count = 0
        for frame in container.decode(stream):
            for sample in resampler.resample(frame):
                time = Fraction(sample.pts or 0) * sample.time_base
                a = max(0, int((Fraction(start_ms, 1000) - time) * 16000))
                b = min(sample.samples, int((Fraction(end_ms, 1000) - time) * 16000))
                if b > a:
                    data = sample.to_ndarray().reshape(-1)[a:b].astype(np.int16)
                    output.writeframes(data.tobytes())
                    count += len(data)
                if time * 1000 >= end_ms:
                    return count
        return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--end-ms", type=int, required=True)
    args = parser.parse_args()
    return 0 if extract(args.source, args.target, args.start_ms, args.end_ms) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
