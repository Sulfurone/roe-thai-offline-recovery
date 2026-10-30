"""Execute the Thai client loader-stage request setter on a synthetic object.

Private client image required; does not call the renderer or write to a running
client. This validates the transition only, not actual model loading.
"""
import json
import struct
from native_codec_probe import NativeCodec, ROOT

c = NativeCodec()
obj = 0x10900000
results = []
for initial, expected in ((0, 1), (1, 1), (2, 2), (3, 3)):
    c.uc.mem_write(obj + 0x48c, struct.pack("<I", initial))
    c.invoke(0xd018f0, obj, [])
    actual = c.read32(obj + 0x48c)
    if actual != expected:
        raise ValueError((initial, actual, expected))
    results.append({"before": initial, "after": actual})
report = {"setter": "0xd018f0", "passed": True, "transitions": results,
          "limitation": "Synthetic object; no rendering or source of request identified"}
(ROOT / "private/typed-gameplay/model-loader-stage-validation.json").write_text(
    json.dumps(report, indent=2), encoding="utf8")
print(json.dumps(report))
