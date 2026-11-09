// 연습 화면 녹음: 마이크만 녹음 > 장이 보일 때마다 시각 기록 > 멈추면 서버로 보내 recordings/<label>/ 에 저장
// 받아쓰기는 하지 않음 (로컬 whisper: recording add --label). practice.js 의 전역(deck · text · elements · currentIndex)을 씀
"use strict";

// 브라우저가 고를 수 있는 녹음 형식 순서 (Chrome·Firefox webm, Safari mp4) > 서버 확장자
const RECORDING_FORMATS = [
  ["audio/webm;codecs=opus", "webm"], ["audio/webm", "webm"], ["audio/mp4", "mp4"], ["audio/ogg;codecs=opus", "ogg"],
];
// 조각 단위 (1초): 멈출 때 마지막 조각까지 받기
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

// 시작: 마이크 권한 > 녹음기 > 지금 장을 0초로 기록
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

// 멈춤 > 업로드 (마이크 해제는 성공·실패 공통)
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
// 녹음 중 페이지를 떠나면 확인 (녹음은 멈추기 전까지 서버에 없음)
window.addEventListener("beforeunload", (event) => { if (isRecording()) event.preventDefault(); });
