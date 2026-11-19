"""Göz Takibi Servisi — OpenCV + Mediapipe FaceMesh → Event Bus.

Faz I:
  EyeTracker sınıfı arka planda kamera okur, kullanıcının bakış yönünü
  normalize edilmiş koordinat olarak (-1.0..+1.0) Event Bus'a yayınlar.
  EYE_TRACKING_ENABLED=false (varsayılan) → servis başlamaz.

  Live2D şu an entegre değil (MP4 video). Koordinatlar frontend'de CSS
  parallax efekti olarak kullanılır; tam Live2D efekti gelecekte eklenir.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import EYE_TRACKING_CAMERA, EYE_TRACKING_FPS

logger = logging.getLogger(__name__)
from app.services.event_bus import bus


def _extract_gaze(face_landmarks, image_w: int, image_h: int) -> tuple[float, float]:
    """Mediapipe FaceMesh landmark'larından bakış koordinatı çıkar.

    Göz merkezini (sol + sağ iris ortalama) al, görüntü boyutuna göre normalize et.
    Döndürülen değerler: (x, y) ∈ [-1.0, 1.0]
    """
    # Sol iris: landmark 468-472 (Mediapipe FaceMesh refined)
    # Sağ iris: landmark 473-477
    # Basit yaklaşım: göz köşelerini kullan (468 ve 473 olmayan landmark'lar her modelde var)
    # Güvenli fallback: burun ucu (landmark 1) ve göz köşeleri (33, 263)
    lm = face_landmarks.landmark

    # Göz merkezleri (yaklaşık)
    left_eye_center_x  = (lm[33].x  + lm[133].x)  / 2
    left_eye_center_y  = (lm[33].y  + lm[133].y)  / 2
    right_eye_center_x = (lm[362].x + lm[263].x) / 2
    right_eye_center_y = (lm[362].y + lm[263].y) / 2

    cx = (left_eye_center_x + right_eye_center_x) / 2
    cy = (left_eye_center_y + right_eye_center_y) / 2

    # 0.5 orta nokta → -1..+1 dönüşümü
    x = (cx - 0.5) * 2.0
    y = (cy - 0.5) * 2.0

    return round(x, 3), round(y, 3)


class EyeTracker:
    """Arka plan kamera döngüsü — göz koordinatlarını Event Bus'a yayınlar."""

    def __init__(self, camera_index: int = EYE_TRACKING_CAMERA, fps: int = EYE_TRACKING_FPS):
        self.camera_index = camera_index
        self.fps = fps
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Arka plan döngüsünü başlat."""
        self._task = asyncio.create_task(self._loop())
        logger.info("Başlatıldı (kamera=%d, fps=%d)", self.camera_index, self.fps)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Durduruldu.")

    async def _loop(self) -> None:
        try:
            import cv2
            import mediapipe as mp
        except ImportError as e:
            logger.error("Bağımlılık eksik: %s. EYE_TRACKING_ENABLED=false yapın.", e)
            return

        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            logger.error("Kamera %d açılamadı.", self.camera_index)
            return

        face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        interval = 1.0 / self.fps
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    await asyncio.sleep(interval)
                    continue

                h, w = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_mesh.process(rgb)

                if results.multi_face_landmarks:
                    gaze_x, gaze_y = _extract_gaze(results.multi_face_landmarks[0], w, h)
                    await bus.publish("live2d", {
                        "params": {
                            "ParamEyeBallX": gaze_x,
                            "ParamEyeBallY": gaze_y,
                        }
                    })
                    logger.debug("gaze x=%+.3f y=%+.3f", gaze_x, gaze_y)

                await asyncio.sleep(interval)
        finally:
            cap.release()
            face_mesh.close()
            logger.info("Kamera kapatıldı.")
