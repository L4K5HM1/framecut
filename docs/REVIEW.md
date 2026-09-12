# Repository preparation notes

## Changes from the supplied app

- Split the Flask coordinator, media processing, template, JavaScript, and CSS into focused files.
- Converted both downloads and exports to background jobs with bounded queueing and locked state.
- Added YouTube-host/video-ID validation, source registration, finite timestamp and caption-type checks, and local-origin restrictions.
- Removed client-visible command traces and enabled bounded subprocess execution.
- Corrected aspect-ratio processing for tall sources, standardized H.264 output, and enabled MP4 fast-start.
- Reused the CPU transcription model, corrected the ASS style header, neutralized subtitle formatting sequences, and used relative ASS paths to avoid drive-letter quoting issues.
- Guaranteed temporary-directory cleanup after success or failure.
- Replaced overlapping polling intervals with sequential polling and added error recovery.
- Added responsive layout, explicit labels, keyboard/touch timeline controls, exact times, and selection preview.
- Fully excluded runtime directories, bytecode, and virtual environments; added setup, license, and regression tests.

## Validation

28 automated tests passed in the preparation environment, including real FFmpeg output for landscape and tall synthetic sources, plus caption burning with a stubbed transcript. Python compilation and JavaScript syntax checks passed.

Live YouTube download, first-time model download, and actual speech recognition were not exercised. Windows-specific execution requires a Windows smoke test even though ASS file-path handling no longer embeds an absolute Windows path in the filter.

The project is published as Framecut. Screenshot and video demo placeholders are intentionally labeled; they do not represent completed demo assets.

Browser visual checks remain unverified because downloading the required Chromium executable timed out. No live YouTube or model download was attempted in the test suite.

## Suggested GitHub metadata

Name: `framecut`

About: Local video-to-shorts editor with a draggable timeline, vertical exports, and automatic captions powered by Flask, FFmpeg, and faster-whisper.

Topics: `python`, `flask`, `ffmpeg`, `faster-whisper`, `video-editing`, `speech-to-text`, `javascript`

## Demo recording checklist

Use footage you own or have permission to share. Show source loading, a timeline adjustment, the captions toggle, and the finished export. Keep the recording concise. Add an actual screenshot or recording to the README; avoid implying a hosted demo exists.
