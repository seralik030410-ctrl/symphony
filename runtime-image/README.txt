Symphony runtime 6.0 - standalone dependency kit

This kit is exported from Symphony. It contains the same Docker recipe used by
the application. No checkout, host Python, host Node.js or Git is required.

1. Install Docker Desktop from https://www.docker.com/products/docker-desktop/
   Start Docker Desktop and wait until its engine is running. On Windows choose
   Linux containers. Check Docker's current system requirements and license.
2. Extract the entire ZIP into a new folder. Do not run files inside the ZIP.
3. macOS: open Terminal in the extracted symphony-runtime folder and run:
       bash INSTALL.sh
   Windows: double-click INSTALL.bat in that folder.
4. Review the prompt and confirm with y. The first build needs Internet and
   several GB of downloads (Docker Hub, Debian and PyPI). Budget at least 12 GB
   of free disk space; actual use varies by architecture and existing cache.
5. Return to Symphony > Settings > General to refresh dependency diagnostics.

The scripts verify SHA256SUMS before building symphony-sandbox:stage3. Hashes
detect corrupt/incomplete extraction, NOT an untrusted publisher. Only run a kit
downloaded from your own trusted Symphony installation. Read the scripts first.
The build can be retried. It updates only the runtime image tag; it does not
delete chats, user files, models, volumes or caches, and does not change Docker
resource/security settings. Custom SYMPHONY_SANDBOX_IMAGE is not reconfigured.

Docker is optional for ordinary conversation. For local model inference install
Ollama from https://ollama.com/download, start it and download a model through
Ollama. Model size is separate from this kit. An API provider needs no Ollama.
API keys, chats, logs, model files and user paths are never included in this kit.

If Docker cannot start, consult Docker's diagnostics; do not reset Docker data
or delete volumes merely to install this runtime. The macOS desktop release
still requires native installer and signing acceptance on a real Mac.
