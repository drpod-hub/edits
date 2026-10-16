"""Run Real-ESRGAN's realesr-general-x4v3 (SRVGGNetCompact) with onnxruntime, no PyTorch needed.

The .pth checkpoint is a torch zip archive; it is read here with a restricted unpickler that only
rebuilds float tensors, then turned into an equivalent ONNX graph:
  33 x (Conv3x3 + PReLU) -> Conv3x3 -> PixelShuffle(4) (DepthToSpace CRD) + nearest-upsampled input.
"""
import io
import os
import pickle
import zipfile

import numpy as np
import onnx
import onnxruntime as ort
from onnx import TensorProto, helper, numpy_helper

_DTYPES = {"FloatStorage": np.float32, "HalfStorage": np.float16}


def load_state_dict(path):
    zf = zipfile.ZipFile(path)
    names = zf.namelist()
    root = names[0].split("/")[0]

    def rebuild(storage, offset, size, stride, *_):
        if not size:
            return np.array(storage[offset])
        view = np.lib.stride_tricks.as_strided(storage[offset:], shape=size,
                                               strides=[st * storage.itemsize for st in stride])
        return np.array(view)

    class U(pickle.Unpickler):
        def find_class(self, mod, name):
            if mod == "torch._utils" and name == "_rebuild_tensor_v2":
                return rebuild
            if mod == "torch" and name in _DTYPES:
                return name
            if mod == "collections" and name == "OrderedDict":
                import collections
                return collections.OrderedDict
            raise pickle.UnpicklingError(f"blocked {mod}.{name}")

        def persistent_load(self, pid):
            _, kind, key, _loc, _n = pid
            raw = zf.read(f"{root}/data/{key}")
            return np.frombuffer(raw, _DTYPES[kind])

    sd = U(io.BytesIO(zf.read(f"{root}/data.pkl"))).load()
    for k in ("params", "params_ema"):
        if isinstance(sd, dict) and k in sd:
            sd = sd[k]
    return {k: v.astype(np.float32) for k, v in sd.items()}


def build_model(sd, up=4):
    nodes, inits = [], []
    x = "input"
    i = 0
    convs = sorted({int(k.split(".")[1]) for k in sd if k.endswith(".bias")})
    for idx in convs:
        w, b = sd[f"body.{idx}.weight"], sd[f"body.{idx}.bias"]
        inits += [numpy_helper.from_array(w, f"w{idx}"), numpy_helper.from_array(b, f"b{idx}")]
        y = f"c{idx}"
        nodes.append(helper.make_node("Conv", [x, f"w{idx}", f"b{idx}"], [y], pads=[1, 1, 1, 1]))
        x = y
        pk = f"body.{idx + 1}.weight"
        if pk in sd and pk.replace(".weight", ".bias") not in sd:  # PReLU slope
            inits.append(numpy_helper.from_array(sd[pk].reshape(-1, 1, 1), f"p{idx}"))
            y = f"a{idx}"
            nodes.append(helper.make_node("PRelu", [x, f"p{idx}"], [y]))
            x = y
    nodes.append(helper.make_node("DepthToSpace", [x], ["ps"], blocksize=up, mode="CRD"))
    inits.append(numpy_helper.from_array(np.array([1, 1, up, up], np.float32), "scales"))
    nodes.append(helper.make_node("Resize", ["input", "", "scales"], ["base"], mode="nearest"))
    nodes.append(helper.make_node("Add", ["ps", "base"], ["output"]))
    g = helper.make_graph(nodes, "srvgg",
                          [helper.make_tensor_value_info("input", TensorProto.FLOAT, ["n", 3, "h", "w"])],
                          [helper.make_tensor_value_info("output", TensorProto.FLOAT, ["n", 3, "H", "W"])], inits)
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 17)])
    m.ir_version = 8
    onnx.checker.check_model(m)
    return m


class Upscaler:
    def __init__(self, weights):
        m = build_model(load_state_dict(weights))
        so = ort.SessionOptions()
        so.intra_op_num_threads = os.cpu_count()
        self.sess = ort.InferenceSession(m.SerializeToString(), so, providers=["CPUExecutionProvider"])

    def __call__(self, frames, bs=4):
        """frames: N x H x W x 3 uint8 -> N x 4H x 4W x 3 uint8"""
        out = []
        for i in range(0, len(frames), bs):
            x = frames[i:i + bs].transpose(0, 3, 1, 2).astype(np.float32) / 255
            y = self.sess.run(None, {"input": x})[0]
            out.append((np.clip(y, 0, 1) * 255 + 0.5).astype(np.uint8).transpose(0, 2, 3, 1))
        return np.concatenate(out)
