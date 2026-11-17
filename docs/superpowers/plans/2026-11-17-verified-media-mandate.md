# Verified media mandate implementation plan

The new user mandate extends the existing platform; do not initialize over or discard the current repository.

- [x] Finish the secondary-worker real MediaMTX smoke test, including AAC RTSP compatibility and last-reader cleanup.
- [x] Configure the six supplied primary HLS sources as continuous pulls; provide native/backend feed catalogs and opt-in ARM64 orchestration. Probe actual sources and preserve evidence rather than assuming all are 1080p.
- [x] Update ingest to explicit audio/video maps, 16 kHz mono PCM, 2 fps lower-20% OCR crops, bounded native thread counts and VideoToolbox option. Keep whole-frame visual tracking separate. Program IDs are only valid on inputs retaining MPEG-TS program tables, not on demuxed local RTSP.
- [x] Replace linear keyword scanning with Aho-Corasick and topic lookup with FAISS, preserving rule semantics and independent completed-window spike baselines.
- [x] Verify supported local Qwen3-ASR/WhisperLiveKit/Silero and PaddleOCR versions; supply launch profiles with no invented backend flags or automatic model download.
- [x] Apply Obsidian Quantum palette and glass surfaces to the existing React command center, preserving RTL and real simulation controls.
- [x] Run backend, frontend, browser, container, controlled media and source checks; document observed hardware and unverified model accuracy/performance.

Execution domains: frontend styling/tests and ASR/OCR profile research are independent delegated tasks; parent owns backend, deployment, integration and final review. Shared schema and API remain stable. Air-gapped analysis and internet acquisition are separate deployment boundaries. Hardware observed locally is Apple M2 Max/64 GiB/arm64; M5 Max is a target, not a tested claim.

Verification: see docs/VERIFICATION.md for actual checks and model/hardware limitations.
