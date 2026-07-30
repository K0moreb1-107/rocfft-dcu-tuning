import pathlib
import subprocess

import numpy as np


root = pathlib.Path(__file__).resolve().parent
length = 524288
rng = np.random.default_rng(20260730)
input_data = (
    rng.standard_normal(length) + 1j * rng.standard_normal(length)
).astype(np.complex128)

input_path = root / "validate_cc512k_input.bin"
output_path = root / "validate_cc512k_output.bin"
input_data.tofile(input_path)

subprocess.run(
    [str(root / "validate_rocfft_512k"), str(input_path), str(output_path)], check=True
)

actual = np.fromfile(output_path, dtype=np.complex128)
expected = np.fft.fft(input_data)
error = actual - expected
relative_l2 = np.linalg.norm(error) / np.linalg.norm(expected)
max_abs = np.max(np.abs(error))
max_reference = np.max(np.abs(expected))
relative_max = max_abs / max_reference

print(f"relative_l2={relative_l2:.6e}")
print(f"relative_max={relative_max:.6e}")
print(f"max_abs={max_abs:.6e}")

if relative_l2 >= 5e-12 or relative_max >= 5e-12:
    raise SystemExit("accuracy check failed")
