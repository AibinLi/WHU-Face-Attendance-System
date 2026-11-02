"""Reproducible weight preparation using pinned public repositories; no recognition API."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANT = 'immich-app/antelopev2/resolve/51ca7e153bccebdbae224779e23c9c243e2fec85/'
ADA = 'minchul/cvlface_adaface_ir101_webface12m/resolve/54f602a0737bd1ee4a4e7e9fd089a485f397fefd/'
FILES = [('models/scrfd_10g.onnx', ANT + 'detection/model.onnx'),
         ('models/arcface_r100.onnx', ANT + 'recognition/model.onnx'),
         ('models/adaface_ir101.safetensors', ADA + 'model.safetensors'),
         ('docs/adaface_architecture.py', ADA + 'models/iresnet/model.py')]


def digest(path):
    hasher=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--endpoint', default='https://hf-mirror.com')
    args=parser.parse_args()
    manifest_path=ROOT/'models/manifest.json'
    manifest=json.loads(manifest_path.read_text('utf8')) if manifest_path.exists() else {}
    for name, remote in FILES:
        path=ROOT/name
        expected=manifest.get(path.name,{}).get('sha256')
        if path.exists() and (expected is None or digest(path)==expected):
            print('Verified existing:',name,flush=True);continue
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix(path.suffix+'.part')
        for attempt in range(3):
            try:
                print('Downloading:',name,flush=True)
                with urllib.request.urlopen(args.endpoint.rstrip('/')+'/'+remote,timeout=60) as response, temporary.open('wb') as output:
                    while True:
                        block=response.read(1024*1024)
                        if not block:break
                        output.write(block)
                if expected and digest(temporary)!=expected:
                    raise ValueError('SHA256 mismatch: '+name)
                if temporary.stat().st_size<1000:
                    raise ValueError('Invalid or incomplete download: '+name)
                temporary.replace(path)
                break
            except Exception:
                if attempt==2:raise
                time.sleep(2)
    if not (ROOT/'models/adaface_ir101.onnx').exists():
        subprocess.run([sys.executable,str(ROOT/'tools/export_adaface.py')],check=True,cwd=ROOT)
    print('Model files ready. See models/SOURCES.md for provenance and usage conditions.')


if __name__=='__main__':main()
