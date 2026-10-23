"""Shot boundaries with PySceneDetect's AdaptiveDetector (04 S6), run on the proxy."""

from __future__ import annotations

from pathlib import Path

from videoflow.analysis.types import EngineInfo, Shot
from videoflow.core import ids
from videoflow.core.time import US_PER_SECOND


def frames_to_us(frame: int, fps: float) -> int:
    return round(frame * US_PER_SECOND / fps)


class SceneDetectShots:
    """:class:`~videoflow.engines.protocols.ShotDetector` backed by PySceneDetect."""

    def __init__(self, *, adaptive_threshold: float = 3.0, min_scene_len: int = 15) -> None:
        self.adaptive_threshold = adaptive_threshold
        self.min_scene_len = min_scene_len
        self.info = EngineInfo(
            engine_id="scenedetect-adaptive",
            model_id=f"t{adaptive_threshold}-min{min_scene_len}",
        )

    def detect(self, video_path: Path, asset_id: str) -> list[Shot]:
        from scenedetect import AdaptiveDetector, SceneManager, open_video

        video = open_video(str(video_path))
        fps = float(video.frame_rate)
        manager = SceneManager()
        manager.add_detector(
            AdaptiveDetector(
                adaptive_threshold=self.adaptive_threshold, min_scene_len=self.min_scene_len
            )
        )
        manager.detect_scenes(video, show_progress=False)
        total_frames = video.position.frame_num + 1  # position is the last decoded frame
        scenes = manager.get_scene_list()
        spans = [(s.frame_num, e.frame_num) for s, e in scenes] if scenes else [(0, total_frames)]
        return [
            Shot(
                id=ids.new_id(ids.SHOT),
                asset_id=asset_id,
                index=i,
                start_us=frames_to_us(s, fps),
                end_us=frames_to_us(e, fps),
            )
            for i, (s, e) in enumerate(spans)
        ]
