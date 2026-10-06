"""
RoninClips — Hardware Acceleration & GPU Detection Module
Probes for NVIDIA CUDA (for Faster-Whisper) and FFmpeg Hardware Encoders
(NVENC / QSV / AMF) with seamless CPU fallback.
"""

import subprocess
import os
import sys

# Cache detection results in-memory
_CUDA_AVAILABLE = None
_CUDA_DEVICE_NAME = None
_FFMPEG_ENCODER = None
_FFMPEG_ENCODER_FLAGS = None


def detect_cuda():
    """
    Check if NVIDIA CUDA is available for Faster-Whisper via ctranslate2 or torch.
    Returns: (is_available: bool, device_name: str)
    """
    global _CUDA_AVAILABLE, _CUDA_DEVICE_NAME
    if _CUDA_AVAILABLE is not None:
        return _CUDA_AVAILABLE, _CUDA_DEVICE_NAME

    # On Windows, verify that cuBLAS runtime DLLs are actually present.
    # Without cublas64_12.dll or cublas64_11.dll, Faster-Whisper / ctranslate2 crashes.
    if sys.platform == 'win32':
        import ctypes
        has_cublas = False
        for dll_name in ['cublas64_12.dll', 'cublas64_11.dll']:
            try:
                ctypes.CDLL(dll_name)
                has_cublas = True
                break
            except Exception:
                continue
        if not has_cublas:
            _CUDA_AVAILABLE = False
            _CUDA_DEVICE_NAME = "CPU"
            return False, "CPU"

    # 1. Try ctranslate2 (used directly by faster-whisper)
    try:
        import ctranslate2
        cuda_count = ctranslate2.get_cuda_device_count()
        if cuda_count > 0:
            _CUDA_AVAILABLE = True
            # Try getting device name from torch or nvidia-smi
            _CUDA_DEVICE_NAME = _get_gpu_name() or f"NVIDIA GPU (CUDA x{cuda_count})"
            return True, _CUDA_DEVICE_NAME
    except Exception:
        pass

    # 2. Try torch dynamically if installed (avoids static linter missing-import error)
    try:
        import importlib
        if importlib.util.find_spec("torch") is not None:
            torch_mod = importlib.import_module("torch")
            if torch_mod.cuda.is_available():
                _CUDA_AVAILABLE = True
                _CUDA_DEVICE_NAME = torch_mod.cuda.get_device_name(0)
                return True, _CUDA_DEVICE_NAME
    except Exception:
        pass

    _CUDA_AVAILABLE = False
    _CUDA_DEVICE_NAME = "CPU"
    return False, "CPU"


def _get_gpu_name():
    """Query nvidia-smi for the primary GPU name."""
    try:
        cmd = "nvidia-smi --query-gpu=name --format=csv,noheader"
        res = subprocess.run(cmd, shell=True, capture_output=True, encoding='utf-8', errors='replace', timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().split('\n')[0].strip()
    except Exception:
        pass
    return None


def get_whisper_config(preferred_accel='auto'):
    """
    Get recommended Faster-Whisper device and compute_type.
    Args:
        preferred_accel: 'auto', 'cuda', 'gpu', or 'cpu'
    Returns:
        dict: {'device': str, 'compute_type': str, 'device_name': str}
    """
    if str(preferred_accel).lower() in ('cpu', 'force_cpu'):
        return {
            'device': 'cpu',
            'compute_type': 'int8',
            'device_name': 'CPU (int8)',
            'is_gpu': False
        }

    has_cuda, gpu_name = detect_cuda()
    if has_cuda:
        return {
            'device': 'cuda',
            'compute_type': 'float16',
            'device_name': f"{gpu_name} (CUDA fp16)",
            'is_gpu': True
        }

    return {
        'device': 'cpu',
        'compute_type': 'int8',
        'device_name': 'CPU (int8)',
        'is_gpu': False
    }


def detect_ffmpeg_encoder(preferred_accel='auto'):
    """
    Test and detect the fastest available hardware H.264 encoder in FFmpeg.
    Returns: (encoder_name: str, encoding_flags: str)
    """
    global _FFMPEG_ENCODER, _FFMPEG_ENCODER_FLAGS
    if _FFMPEG_ENCODER is not None and preferred_accel == 'auto':
        return _FFMPEG_ENCODER, _FFMPEG_ENCODER_FLAGS

    if str(preferred_accel).lower() in ('cpu', 'force_cpu'):
        _FFMPEG_ENCODER = 'libx264'
        _FFMPEG_ENCODER_FLAGS = '-c:v libx264 -preset medium -crf 22 -profile:v high -level 4.0 -pix_fmt yuv420p'
        return _FFMPEG_ENCODER, _FFMPEG_ENCODER_FLAGS

    # Check ffmpeg -encoders output
    try:
        res = subprocess.run('ffmpeg -encoders', shell=True, capture_output=True, encoding='utf-8', errors='replace', timeout=5)
        encoders_output = res.stdout or ''
    except Exception:
        encoders_output = ''

    # Candidate hardware encoders in order of priority
    candidates = [
        ('h264_nvenc', '-c:v h264_nvenc -preset p4 -cq 22 -pix_fmt yuv420p'),
        ('h264_qsv', '-c:v h264_qsv -global_quality 22 -pix_fmt yuv420p'),
        ('h264_amf', '-c:v h264_amf -quality speed -rc cqp -qp_i 22 -qp_p 22 -pix_fmt yuv420p'),
    ]

    null_sink = 'NUL' if sys.platform == 'win32' else '/dev/null'

    for encoder, flags in candidates:
        if encoder in encoders_output:
            # Fast test render to verify actual hardware driver support
            try:
                test_cmd = f'ffmpeg -f lavfi -i testsrc=duration=0.1:size=64x64:rate=30 -c:v {encoder} -f null {null_sink} -y'
                probe = subprocess.run(
                    test_cmd, shell=True, capture_output=True,
                    encoding='utf-8', errors='replace', timeout=4
                )
                if probe.returncode == 0:
                    _FFMPEG_ENCODER = encoder
                    _FFMPEG_ENCODER_FLAGS = flags
                    return encoder, flags
            except Exception:
                continue

    # Fallback to standard CPU libx264
    _FFMPEG_ENCODER = 'libx264'
    _FFMPEG_ENCODER_FLAGS = '-c:v libx264 -preset medium -crf 22 -profile:v high -level 4.0 -pix_fmt yuv420p'
    return _FFMPEG_ENCODER, _FFMPEG_ENCODER_FLAGS



def get_hardware_status():
    """Returns a dictionary summary of hardware capabilities for logging/UI."""
    cuda_avail, gpu_name = detect_cuda()
    encoder, enc_flags = detect_ffmpeg_encoder()
    return {
        'cuda_available': cuda_avail,
        'gpu_name': gpu_name,
        'ffmpeg_encoder': encoder,
        'is_hardware_accelerated': cuda_avail or encoder != 'libx264'
    }


if __name__ == '__main__':
    status = get_hardware_status()
    print("=== RoninClips Hardware Diagnostics ===")
    print(f"CUDA Available:   {status['cuda_available']}")
    print(f"GPU Device:       {status['gpu_name']}")
    print(f"FFmpeg Encoder:   {status['ffmpeg_encoder']}")
    print(f"HW Accelerated:   {status['is_hardware_accelerated']}")
