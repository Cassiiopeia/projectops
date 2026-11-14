// Practice screen recording: mic only > log a timestamp each time a slide shows > on stop, send to the server and save under recordings/<label>/
// No transcription here (local whisper: recording add --label). Uses practice.js globals (deck · text · elements · currentIndex)
"use strict";

// Recording formats the browser may pick, in order (Chrome/Firefox webm, Safari mp4) > server extension
const RECORDING_FORMATS = [
  ["audio/webm;codecs=opus", "webm"], ["audio/webm", "webm"], ["audio/mp4", "mp4"], ["audio/ogg;codecs=opus", "ogg"],
];
// Chunk size (1 second): receive up to the last chunk on stop
const RECORDING_SLICE_MILLISECONDS = 1000;

let mediaRecorder = null;
let recordingStartedAt = 0;
let recordingMarks = [];
let recordingChunks = [];

const isRecording = () => mediaRecorder?.state === "recording";
const recordingElapsedSeconds = () => (performance.now() - recordingStartedAt) / 1000;

function pickRecordingFormat() {
  if (typeof MediaRecorder === "undefined") return null;
  return RECORDING_FORMATS.find(([mimeType]) => MediaRecorder.isTypeSupported(mimeType)) ?? null;
}

function markSlide(slideId) {
  if (!isRecording() || recordingMarks.at(-1)?.slide === slideId) return;
  recordingMarks.push({ slide: slideId, at: Math.round(recordingElapsedSeconds() * 10) / 10 });
}

function setRecordStatus(message, isError = false) {
  elements.saveStatus.classList.toggle("error", isError);
  elements.saveStatus.textContent = message;
}

// Start: mic permission > recorder > log the current slide as 0 seconds
async function startRecording() {
  const format = pickRecordingFormat();
  if (!format) return setRecordStatus(text.record_unsupported, true);
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    return setRecordStatus(text.mic_denied, true);
  }
  recordingChunks = [];
  recordingMarks = [];
  mediaRecorder = new MediaRecorder(stream, { mimeType: format[0] });
  mediaRecorder.extension = format[1];
  mediaRecorder.addEventListener("dataavailable", (event) => { if (event.data.size) recordingChunks.push(event.data); });
  mediaRecorder.addEventListener("stop", () => uploadRecording(stream));
  mediaRecorder.start(RECORDING_SLICE_MILLISECONDS);
  recordingStartedAt = performance.now();
  markSlide(deck.slides[currentIndex].id);
  setRecordStatus("");
  document.body.classList.add("recording-live");
  renderRecordButton();
}

// Stop > upload (mic release on success and failure alike)
async function uploadRecording(stream) {
  const durationSeconds = recordingElapsedSeconds();
  stream.getTracks().forEach((track) => track.stop());
  document.body.classList.remove("recording-live");
  renderRecordButton();
  setRecordStatus(text.recording_saving);
  const blob = new Blob(recordingChunks, { type: mediaRecorder.mimeType });
  const marks = encodeURIComponent(JSON.stringify({ duration: durationSeconds, marks: recordingMarks }));
  try {
    const response = await fetch(`/api/recording?ext=${mediaRecorder.extension}`, {
      method: "POST", headers: { "Content-Type": blob.type || "application/octet-stream", "X-Recording-Marks": marks }, body: blob,
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) return setRecordStatus(`${text.recording_failed} (${result.code ?? response.status})`, true);
    setRecordStatus(`${text.recording_saved}: ${result.label} · ${formatSeconds(result.duration_seconds)}`);
    await fetchDeck();
    showSlide(currentIndex);
  } catch {
    setRecordStatus(text.recording_failed, true);
  }
}

function renderRecordButton() {
  elements.recordToggle.classList.toggle("live", isRecording());
  elements.recordToggle.textContent = isRecording() ? `${text.stop_recording} ${formatSeconds(recordingElapsedSeconds())}` : text.record;
}

elements.recordToggle.addEventListener("click", () => (isRecording() ? mediaRecorder.stop() : startRecording()));
window.addEventListener("slide-shown", (event) => markSlide(event.detail));
setInterval(() => { if (isRecording()) renderRecordButton(); }, 500);
// Confirm before leaving the page while recording (the recording is not on the server until stopped)
window.addEventListener("beforeunload", (event) => { if (isRecording()) event.preventDefault(); });
