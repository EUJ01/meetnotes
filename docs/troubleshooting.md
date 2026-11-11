# Troubleshooting

- Start with `meetnotes doctor`. Each failed check prints a fix.
- `PyTorch ... CPU-only` on a machine with a GPU: reinstall PyTorch for your GPU (README, Install, step 3).
- The transcript is in the wrong language: run it again with `--language <code> --force`.
- `... belongs to another recording or length`: a transcript with that name exists. Use `--out` or `--force`.
- LM Studio on Windows says `listen EACCES: permission denied 127.0.0.1:1234`: Windows reserved that port (Hyper-V, WSL and Docker reserve port ranges). Check with `netsh interface ipv4 show excludedportrange protocol=tcp`, pick a port outside the ranges (for example 8765) in LM Studio's server settings, and use it in `base_url`.
- Windows with an AMD GPU: the ROCm runtime can hang when Python exits. meetnotes ends its own process after the work is done to avoid this.

## Development

```
python -m unittest discover -s tests -t .
```

The tests need no GPU, network or ffmpeg. `tests/test_secrets.py` fails if a file holds something that looks like a token. Keep secrets in environment variables.
