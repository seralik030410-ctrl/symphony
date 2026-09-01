"""Export a fixed, inspectable runtime recipe; never install/execute on the host."""
import hashlib
import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response

from backend.config import PROJECT_ROOT

router = APIRouter(prefix="/api/setup")
KIT_FILES = ("Dockerfile", "requirements.txt", "INSTALL.sh", "INSTALL.ps1", "INSTALL.bat", "README.txt")
KIT_ROOT = PROJECT_ROOT / "runtime-image"


def runtime_kit(root: Path) -> bytes:
    payloads = {}
    try:
        for name in KIT_FILES:
            path = root / name
            if path.is_symlink() or path.resolve().parent != root.resolve() or not path.is_file() or path.stat().st_size > 256_000:
                raise OSError("Invalid packaged runtime resource")
            payloads[name] = path.read_bytes()
    except OSError as exc:
        raise HTTPException(503, "Runtime kit is missing or incomplete. Reinstall Symphony; no host changes were made.") from exc
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in payloads.items()}
    payloads["SHA256SUMS"] = "".join(f"{sha}  {name}\n" for name, sha in hashes.items()).encode()
    payloads["manifest.json"] = json.dumps({"schema_version": 1, "runtime_version": "6.0", "image": "symphony-sandbox:stage3", "sha256": hashes}, indent=2).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in payloads.items():
            entry = zipfile.ZipInfo("symphony-runtime/" + name)
            entry.create_system = 3
            entry.external_attr = (0o100755 if name == "INSTALL.sh" else 0o100644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, content)
    return output.getvalue()


@router.get("/runtime-kit")
async def download_runtime_kit():
    return Response(runtime_kit(KIT_ROOT), media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="symphony-runtime-6.0.zip"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })
